"""新增菜单/报表：同步后本机验尸。

禁止假成功：「交付写已上菜单 / 视图已同步，但 catalog.menu 仍为 false
或接线文件仍在 deferred」。

意图须收紧：仅「新增/添加…菜单|报表」类诉求触发 catalog 可见性检查，
避免「修复日产报表」误杀 menu:false 的隐藏项。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .path_scope import is_ui_shell_wiring, normalize_rel

_CATALOG_RELS = (
    "frontend/src/config/reportFeatures.js",
    "frontend/src/config/reportFeatures.ts",
)

# 必须同时具备「新增类」与「菜单/报表语境」
_ADD_EXPLICIT = ("新增", "添加", "加上", "开通")
_MENU_CTX = ("菜单", "报表", "侧栏", "侧边栏", "导航", "路由")
_EXCLUDE = ("删除", "移除", "去掉", "隐藏", "下线", "修复", "重构", "bugfix")


def _is_add_menu_intent(requirement: str) -> bool:
    text = str(requirement or "").strip()
    if not text:
        return False
    if any(k in text for k in _EXCLUDE):
        return False
    has_add = any(k in text for k in _ADD_EXPLICIT)
    has_ctx = any(k in text for k in _MENU_CTX)
    return has_add and has_ctx


def _synced_rels(synced_files: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in synced_files or []:
        s = str(raw or "").strip().replace("\\", "/")
        if not s or s.startswith("删除 "):
            continue
        rel = normalize_rel(s)
        if rel:
            out.append(rel)
    return out


def deferred_wiring_blockers(deferred_files: list[str] | None) -> list[str]:
    """仍 deferred 的接线文件 → 禁止任务报成功。"""
    bad: list[str] = []
    for raw in deferred_files or []:
        rel = normalize_rel(str(raw or ""))
        if not rel:
            continue
        if is_ui_shell_wiring(rel) or rel.startswith("frontend/src/config/"):
            bad.append(rel)
    return bad


def _parse_catalog_blocks(text: str) -> list[dict[str, Any]]:
    """从 reportFeatures 风格 catalog 抽出 id / viewFile / menu。

    按「含 viewFile 的对象」定位：向前取最近 ``{``、向后取配对 ``}``，
    避免嵌套 ``{}`` 时整段被扁平正则丢掉。
    """
    entries: list[dict[str, Any]] = []
    for vf_m in re.finditer(r"""\bviewFile\s*:\s*['"]([^'"]+)['"]""", text):
        view_file = vf_m.group(1).strip()
        start = text.rfind("{", 0, vf_m.start())
        if start < 0:
            continue
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            continue
        block = text[start : end + 1]
        eid = ""
        menu_val: bool | None = None
        id_m = re.search(r"""\bid\s*:\s*['"]([^'"]+)['"]""", block)
        if id_m:
            eid = id_m.group(1).strip()
        menu_m = re.search(r"""\bmenu\s*:\s*(true|false)""", block, flags=re.I)
        if menu_m:
            menu_val = menu_m.group(1).lower() == "true"
        title = ""
        title_m = re.search(r"""\btitle\s*:\s*['"]([^'"]+)['"]""", block)
        if title_m:
            title = title_m.group(1).strip()
        entries.append(
            {"id": eid, "viewFile": view_file, "menu": menu_val, "title": title}
        )
    return entries


def _read_catalog(target: Path) -> tuple[Path | None, str, list[dict[str, Any]]]:
    for rel in _CATALOG_RELS:
        path = target / rel
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return path, "", []
            return path, text, _parse_catalog_blocks(text)
    return None, "", []


def _corpus_mentions_entry(corpus: str, entry: dict[str, Any]) -> bool:
    """需求正文是否点名该 catalog 项（id / 去连字符 id / 中文 title）。"""
    c = corpus.replace(" ", "")
    eid = str(entry.get("id") or "")
    title = str(entry.get("title") or "")
    if eid:
        compact = eid.replace("-", "").replace("_", "")
        if eid in corpus or (compact and compact in c.replace("-", "").replace("_", "")):
            return True
    if title and title in corpus:
        return True
    # 常见别名
    if "日产" in corpus and eid in {"daily-output", "daily_output"}:
        return True
    if "工时" in corpus and "employee" in eid.replace("-", ""):
        return True
    if "在制品" in corpus and eid in {"wip"}:
        return True
    return False


def verify_add_menu_on_target(
    target_root: Path,
    requirement: str,
    *,
    synced_files: list[str] | None = None,
    deferred_files: list[str] | None = None,
) -> dict[str, Any]:
    """新增菜单/报表后验尸。

    失败条件：
    1. 接线/config 仍在 deferred（任意任务）
    2. 明确「新增菜单/报表」且已同步 reports 视图，但 catalog 未注册或 menu:false
    """
    blockers = deferred_wiring_blockers(deferred_files)
    if blockers:
        return {
            "ok": False,
            "detail": (
                "菜单/路由配置未同步到本机（仍 deferred）："
                + "、".join(blockers[:8])
                + "。禁止报成功；请扩大写范围或重新开工。"
            ),
        }

    if not _is_add_menu_intent(requirement):
        return {"ok": True, "detail": ""}

    target = Path(target_root).resolve()
    synced = _synced_rels(synced_files)
    report_views = [
        r
        for r in synced
        if r.startswith("frontend/src/views/reports/") and r.endswith(".vue")
    ]
    catalog_touched = any(r.startswith("frontend/src/config/") for r in synced)

    if not report_views and not catalog_touched:
        return {"ok": True, "detail": ""}

    catalog_path, _text, entries = _read_catalog(target)
    if catalog_path is None:
        return {"ok": True, "detail": ""}

    by_view = {str(e.get("viewFile") or ""): e for e in entries if e.get("viewFile")}
    problems: list[str] = []
    for rel in report_views:
        view_file = rel.rsplit("/", 1)[-1]
        entry = by_view.get(view_file)
        if not entry:
            problems.append(f"{view_file} 已同步但 {catalog_path.name} 未注册")
            continue
        if entry.get("menu") is False:
            eid = entry.get("id") or view_file
            problems.append(
                f"{catalog_path.name} 中「{eid}」仍为 menu:false（侧栏不会出现）"
            )

    # 只改了 catalog：按需求点名的项检查 menu
    if catalog_touched and not report_views:
        corpus = str(requirement or "")
        for e in entries:
            if _corpus_mentions_entry(corpus, e) and e.get("menu") is False:
                eid = e.get("id") or e.get("viewFile") or "?"
                problems.append(
                    f"{catalog_path.name} 中「{eid}」仍为 menu:false（侧栏不会出现）"
                )

    if problems:
        return {
            "ok": False,
            "detail": "；".join(problems[:8]) + "。禁止假成功，请修好 catalog 后重试。",
        }
    return {"ok": True, "detail": "本机菜单验尸通过"}
