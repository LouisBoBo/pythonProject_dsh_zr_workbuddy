"""删除类任务：Cursor 未物理删文件时，由引擎在沙箱/本机强制执行删除并修补菜单路由。"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable

from .brief import extract_claimed_deleted_paths, is_delete_intent
from .delete_verify import _FEATURE_ORPHAN_FILES, _FEATURE_ROUTE_MARKERS, extract_delete_features
from .sandbox import is_sensitive_rel

Sink = Callable[[dict[str, Any]], None]

_MENU_FILES = (
    "frontend/src/layouts/AppLayout.vue",
    "frontend/src/router/index.js",
)

_BLOCK_DELETE_FILES = frozenset(
    {
        "frontend/src/layouts/AppLayout.vue",
        "frontend/src/router/index.js",
        "frontend/src/main.js",
        "frontend/package.json",
        "package.json",
    }
)

_MAX_PLAN_FILES = 24


_MENU_ROUTER_FILES = frozenset(
    {
        "frontend/src/layouts/AppLayout.vue",
        "frontend/src/router/index.js",
    }
)

# 保护名单：永不物理删除（共用入口/设备点检等）
_PROTECTED_BASENAMES = frozenset(
    {
        "InspectionEntryView.vue",
        "inspection.js",
        "main.js",
        "main.ts",
        "main.py",  # 仅段修补，禁止整文件删除
        "App.vue",
        "package.json",
        "vite.config.js",
        "vite.config.ts",
        "schemas.py",
        "openapi_zh.py",
    }
)

# 共用模块：过程清单即使列出也禁止整文件删除（须段修补或跳过）
_SHARED_WHOLE_FILE_DENY = frozenset(
    {
        # 前端共用封装
        "warehouse.js",
        "inspection.js",
        "qualityInspectionRecords.js",
        "request.js",
        "http.js",
        "axios.js",
        "client.js",
        "api.js",
        "auth.js",
        "main.js",
        "main.ts",
        "App.vue",
        "AppLayout.vue",
        "index.js",
        "package.json",
        # 后端共用壳 / 多功能同文件
        "main.py",
        "schemas.py",
        "openapi_zh.py",
        "auth.py",
        "dashboard.py",
        "warehouse.py",
        "production.py",
        "quality.py",
        "inspection.py",
        "equipment.py",
        "messages.py",
        "reports.py",
        "work_orders.py",
        "devices.py",
    }
)

# 删除功能后须从 backend/app/main.py 卸掉的 router 模块名（仅兜底；主路径从已删 routers/*.py 推导）
_FEATURE_MAIN_ROUTER_MODS: dict[str, tuple[str, ...]] = {}

_MAIN_PY_REL = "backend/app/main.py"


# 删除铁律：白名单优先；不确定不删。禁止扫盘猜测。


def plan_delete_file_targets(requirement: str, target_root: Path) -> list[str]:
    """引擎可删文件清单：仅功能白名单中登记且本机存在的路径。

    不含菜单/路由壳文件（由修补逻辑处理）。未登记功能 → 空清单（只补菜单，不删文件）。
    """
    if not is_delete_intent(requirement):
        return []
    root = Path(target_root).resolve()
    features = extract_delete_features(requirement)
    rels: list[str] = []
    seen: set[str] = set()

    for feat in features:
        for rel in _FEATURE_ORPHAN_FILES.get(feat, ()):
            r = str(rel or "").replace("\\", "/").strip().lstrip("/")
            if not r or r in seen or r in _MENU_ROUTER_FILES or r in _BLOCK_DELETE_FILES:
                continue
            if Path(r).name in _PROTECTED_BASENAMES:
                continue
            if not (root / r).is_file():
                continue
            seen.add(r)
            rels.append(r)
            if len(rels) >= _MAX_PLAN_FILES:
                return rels
    return rels


def _rel_is_protected(rel: str) -> bool:
    r = str(rel or "").replace("\\", "/").strip().lstrip("./")
    if not r:
        return True
    if r in _BLOCK_DELETE_FILES or r in _MENU_ROUTER_FILES:
        return True
    if Path(r).name in _PROTECTED_BASENAMES:
        return True
    if ".." in Path(r).parts:
        return True
    return False


def _safe_file_under_root(root: Path, rel: str) -> Path | None:
    """解析相对路径并强制落在 root 内，防 `frontend/../../etc/passwd` 穿越。"""
    r = str(rel or "").replace("\\", "/").strip().lstrip("./")
    if not r or _rel_is_protected(r) or is_sensitive_rel(r):
        return None
    if ".." in Path(r).parts:
        return None
    root_r = root.resolve()
    try:
        cand = (root_r / r).resolve()
        cand.relative_to(root_r)
    except (OSError, ValueError):
        return None
    if not cand.is_file():
        return None
    return cand


def _cursor_path_high_confidence(rel: str, root: Path, features: list[str]) -> bool:
    """Cursor 额外路径：仅「Vue 文件名 token + 页标题」双重命中才放行；API 一律不靠猜。"""
    r = str(rel or "").replace("\\", "/").strip().lstrip("./")
    if not r or _rel_is_protected(r):
        return False
    if r.endswith((".js", ".ts", ".tsx", ".mjs", ".cjs")):
        return False
    if not r.endswith(".vue"):
        return False
    p = root / r
    if not p.is_file():
        return False
    try:
        body = p.read_text(encoding="utf-8", errors="replace")[:8000]
    except OSError:
        return False
    return any(_vue_is_primary_feature_page(p, body, feat) for feat in features)


def _vue_is_primary_feature_page(path: Path, body: str, feat: str) -> bool:
    """主页面判定：须文件名 token 命中，且页标题等于功能名。未登记 token → 不确定 → False。"""
    if not feat:
        return False
    stem = path.stem.lower().replace("_", "").replace("-", "")
    feat_tokens = {
        "检验记录": ("inspectionrecords",),
        "检验任务": ("inspectiontasks",),
        "检验方案": ("inspectionplans",),
        "品质概览": ("qualityoverview",),
        "生产排产": ("productionscheduling", "scheduling"),
        "仓储看板": ("warehousedashboard", "warehousekanban"),
        "生产看板": ("productiondashboard", "productionkanban"),
        "品质看板": ("qualitydashboard", "qualitykanban"),
        "设备看板": ("devicedashboard", "equipmentkanban"),
        "综合看板": ("generaldashboard", "comprehensivekanban"),
    }
    tokens = feat_tokens.get(feat)
    if not tokens:
        return False
    if not any(tok in stem for tok in tokens):
        return False
    # 看板类页常无 page-title，文件名 token + 白名单已足够
    if feat.endswith("看板"):
        return True
    if re.search(rf'class="page-title"[^>]*>\s*{re.escape(feat)}\s*<', body):
        return True
    if re.search(rf'<h1[^>]*class="page-title"[^>]*>\s*{re.escape(feat)}\s*<', body):
        return True
    if re.search(rf"<h1[^>]*>\s*{re.escape(feat)}\s*</h1>", body):
        return True
    return False


def _cursor_plan_path_ok(rel: str, root: Path, features: list[str]) -> bool:
    """过程「删除清单」路径：专属 API/路由放行；页面须与当前功能相关，禁止误删兄弟页。"""
    r = str(rel or "").replace("\\", "/").strip().lstrip("./")
    if not r or _rel_is_protected(r):
        return False
    base = Path(r).name
    deny = {x.lower() for x in _SHARED_WHOLE_FILE_DENY}
    if base.lower() in deny:
        return False
    if not (root / r).is_file():
        return False
    if _safe_file_under_root(root, r) is None:
        return False
    # 专属 API / 后端路由整文件：过程已论证且非共用壳 → 放行（不写死功能名）
    if r.startswith("frontend/src/api/") and r.endswith((".js", ".ts", ".mjs", ".cjs")):
        return True
    if r.startswith("backend/app/routers/") and r.endswith(".py") and base != "__init__.py":
        return True
    # 页面：必须与待删功能相关（高置信主页面），避免兄弟页被清单误带
    if r.endswith(".vue") and "/views/" in r:
        return _cursor_path_high_confidence(r, root, features)
    return _cursor_path_high_confidence(r, root, features)


def parse_delete_plan_from_text(text: str) -> list[str]:
    """从 Cursor 删除定位终稿 / 过程正文解析相对路径。"""
    body = text or ""
    m = re.search(r"#{1,3}\s*删除清单", body)
    if m:
        body = body[m.end() :]
    elif "删除清单" in body:
        body = body.split("删除清单", 1)[1]
    stop = re.search(r"(?:^|\n)\s*结论\s*[：:]", body)
    if stop:
        body = body[: stop.start()]
    out: list[str] = []
    seen: set[str] = set()

    def _add(rel: str) -> None:
        r = str(rel or "").replace("\\", "/").strip().lstrip("./").strip("`")
        if r:
            r = re.split(r"[：:\s]", r, maxsplit=1)[0].strip()
        if not r or r in seen:
            return
        if ".." in Path(r).parts:
            return
        if not re.search(r"(frontend|backend|apps|src)/", r):
            return
        if not re.search(r"\.[A-Za-z0-9]+$", r):
            return
        seen.add(r)
        out.append(r)

    for m in re.finditer(r"`((?:frontend|backend|apps|src)/[^`]+)`", body):
        _add(m.group(1))
    for m in re.finditer(
        r"(?:^|[\s\-])((?:frontend|backend|apps|src)/[\w./@-]+\.[A-Za-z0-9]+)",
        body,
        re.M,
    ):
        _add(m.group(1))
    if not out:
        for rel in extract_claimed_deleted_paths(text or ""):
            _add(rel)
    return out[:_MAX_PLAN_FILES]


def extract_deleted_paths_from_process(text: str) -> list[str]:
    """从过程正文提取删除清单 +「已删除」路径，保持出现顺序。"""
    body = text or ""
    out: list[str] = []
    seen: set[str] = set()

    def _add(rel: str) -> None:
        r = str(rel or "").replace("\\", "/").strip().lstrip("./").strip("`")
        if r:
            r = re.split(r"[：:\s]", r, maxsplit=1)[0].strip()
        if not r or r in seen:
            return
        if not re.search(r"(frontend|backend|apps|src)/", r):
            return
        seen.add(r)
        out.append(r)

    for rel in parse_delete_plan_from_text(body):
        _add(rel)
    for m in re.finditer(
        r"(?:已删除|引擎已删除|准备删除|将删除)\s*`((?:frontend|backend|apps|src)/[^`]+)`",
        body,
    ):
        _add(m.group(1))
    return out[:_MAX_PLAN_FILES]


def align_delivery_files_with_process(
    process_text: str,
    *,
    deleted: list[str],
    patched: list[str],
) -> tuple[list[str], list[str]]:
    """结论改动文件：按过程清单顺序对齐实际落盘，再补过程未列但已执行的项。"""
    del_norm = [
        str(x).replace("\\", "/").strip().lstrip("./")
        for x in (deleted or [])
        if str(x).strip()
    ]
    del_set = set(del_norm)
    ordered: list[str] = []
    for rel in extract_deleted_paths_from_process(process_text):
        if rel in del_set and rel not in ordered:
            ordered.append(rel)
    for rel in del_norm:
        if rel not in ordered:
            ordered.append(rel)
    pats = [
        str(x).replace("\\", "/").strip().lstrip("./")
        for x in (patched or [])
        if str(x).strip()
        and str(x).replace("\\", "/").strip().lstrip("./") not in set(ordered)
    ]
    return ordered, list(dict.fromkeys(pats))


def validate_delete_plan(
    paths: list[str],
    requirement: str,
    target_root: Path,
    *,
    write_scope: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """校验待删清单；返回 (批准路径, 拒绝原因)。

    铁律：引擎白名单必批；过程删除清单中的专属页/API/路由在写范围内放行；
    共用壳文件与越界路径拒绝。
    """
    root = Path(target_root).resolve()
    approved: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()

    def approve(rel: str) -> None:
        r = rel.replace("\\", "/").strip().lstrip("./")
        if not r or r in seen:
            return
        seen.add(r)
        approved.append(r)

    features = extract_delete_features(requirement)
    engine_floor = plan_delete_file_targets(requirement, root)
    floor_set = set(engine_floor)

    for rel_n in engine_floor:
        if _rel_is_protected(rel_n) or is_sensitive_rel(rel_n):
            rejected.append(f"{rel_n}：保护/敏感路径，跳过")
            continue
        if write_scope:
            ws = [str(x).replace("\\", "/").strip().rstrip("/") for x in write_scope if x]
            in_scope = any(
                rel_n == p or rel_n.startswith(p + "/") for p in ws
            )
            if not in_scope:
                rejected.append(f"{rel_n}：不在 write_scope（白名单项仍拒绝越界）")
                continue
        if ".." in Path(rel_n).parts or _safe_file_under_root(root, rel_n) is None:
            # 白名单项也须真实存在且不越界
            if ".." in Path(rel_n).parts:
                rejected.append(f"{rel_n}：非法相对路径")
            elif not (root / rel_n).is_file():
                continue
            else:
                rejected.append(f"{rel_n}：越出工程根目录")
                continue
        approve(rel_n)
        if len(approved) >= _MAX_PLAN_FILES:
            return approved, rejected

    for rel in list(paths or []):
        rel_n = str(rel or "").replace("\\", "/").strip().lstrip("./")
        if not rel_n or rel_n in seen:
            continue
        if rel_n in _BLOCK_DELETE_FILES or rel_n in _MENU_ROUTER_FILES:
            rejected.append(f"{rel_n}：菜单/路由由引擎修补，禁止整文件删除")
            continue
        if _rel_is_protected(rel_n) or is_sensitive_rel(rel_n):
            rejected.append(f"{rel_n}：保护/敏感路径，拒绝删除")
            continue
        if ".." in Path(rel_n).parts:
            rejected.append(f"{rel_n}：非法相对路径")
            continue
        tg = _safe_file_under_root(root, rel_n)
        if tg is None:
            rejected.append(f"{rel_n}：本机不存在或越出工程根目录")
            continue
        if rel_n in floor_set:
            continue
        if write_scope:
            ws = [str(x).replace("\\", "/").strip().rstrip("/") for x in write_scope if x]
            in_scope = any(
                rel_n == p or rel_n.startswith(p + "/") for p in ws
            )
            if not in_scope:
                rejected.append(f"{rel_n}：不在 write_scope")
                continue
        if _cursor_plan_path_ok(rel_n, root, features):
            approve(rel_n)
        else:
            rejected.append(f"{rel_n}：不确定，拒绝删除（共用壳或不支持整删类型）")
        if len(approved) >= _MAX_PLAN_FILES:
            break

    return approved, rejected


def restore_sandbox_scope_from_target(
    sandbox: Path,
    target: Path,
    rels: list[str],
) -> None:
    """Cursor 定位若误改沙箱，执行前从本机工程还原。"""
    sandbox = sandbox.resolve()
    target = target.resolve()
    for rel in rels or []:
        rel_n = str(rel or "").replace("\\", "/").strip().lstrip("./")
        if not rel_n:
            continue
        tg = target / rel_n
        sb = sandbox / rel_n
        if tg.is_file():
            sb.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(tg, sb, follow_symlinks=False)
            except OSError:
                pass
        elif sb.is_file():
            try:
                sb.unlink()
            except OSError:
                pass


def _ensure_file_in_sandbox(sandbox: Path, target: Path, rel: str) -> bool:
    rel_n = rel.replace("\\", "/").lstrip("/")
    sb = sandbox / rel_n
    tg = target / rel_n
    if sb.is_file():
        return True
    if not tg.is_file():
        return False
    sb.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(tg, sb, follow_symlinks=False)
        return True
    except OSError:
        return False


def _delete_file(path: Path) -> bool:
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError:
        return False
    return False


def _strip_menu_lines(text: str, feature: str) -> tuple[str, bool]:
    if not text or not feature:
        return text, False
    changed = False
    lines: list[str] = []
    markers = _FEATURE_ROUTE_MARKERS.get(feature, ())
    for line in text.splitlines():
        drop = False
        if re.search(rf"title:\s*['\"]{re.escape(feature)}['\"]", line):
            drop = True
        if not drop:
            for mk in markers:
                if mk.lower() in line.lower():
                    drop = True
                    break
        if drop:
            changed = True
            continue
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), changed


def _extract_balanced_object(text: str, start: int) -> tuple[str, int] | None:
    """从 text[start]=='{' 起取出平衡大括号对象，返回 (片段, 结束下标)。"""
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    i = start
    in_str: str | None = None
    escape = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            in_str = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                # 吞掉尾随逗号与空白
                j = end
                while j < len(text) and text[j] in " \t":
                    j += 1
                if j < len(text) and text[j] == ",":
                    end = j + 1
                return text[start:end], end
        i += 1
    return None


def _strip_router_blocks(text: str, feature: str) -> tuple[str, bool]:
    """按标记删除路由对象（支持 meta: { ... } 嵌套），避免留下半截 {{。"""
    if not text or not feature:
        return text, False
    markers = list(_FEATURE_ROUTE_MARKERS.get(feature, ()))
    if feature == "检验方案":
        markers.append("inspection-plans")
    elif feature == "检验任务":
        markers.extend(["inspection-tasks", "quality-inspection-tasks"])
    elif feature == "检验记录":
        markers.extend(["inspection-records", "quality-inspection-records"])
    elif feature == "品质概览":
        markers.extend(["QualityOverview", "quality-overview"])
    elif feature == "生产排产":
        markers.extend(["production/scheduling", "production-scheduling", "ProductionScheduling"])
    if not markers:
        return text, False

    changed = False
    out = text
    # 反复扫描：定位含标记的 `{` 对象并整块删除
    for _ in range(12):
        removed = False
        lower = out.lower()
        for mk in markers:
            key = mk.lower()
            pos = 0
            while True:
                hit = lower.find(key, pos)
                if hit < 0:
                    break
                # 回退到本对象起始 `{`
                brace = out.rfind("{", 0, hit)
                if brace < 0:
                    pos = hit + len(key)
                    continue
                extracted = _extract_balanced_object(out, brace)
                if not extracted:
                    pos = hit + len(key)
                    continue
                block, end = extracted
                # 必须是路由项：标记出现在 path/name/component/title
                if not re.search(
                    rf"(path|name|component|redirect|title)\s*:\s*.*{re.escape(mk)}",
                    block,
                    re.I | re.S,
                ):
                    pos = hit + len(key)
                    continue
                out = out[:brace] + out[end:]
                lower = out.lower()
                changed = True
                removed = True
                break
            if removed:
                break
        if not removed:
            break

    cleaned, c2 = _cleanup_router_shell(out)
    return cleaned, changed or c2


def _cleanup_router_shell(text: str) -> tuple[str, bool]:
    """去掉剥离后留下的空路由对象 / 残缺逗号，并补全 quality-management 重定向。"""
    if not text:
        return text, False
    changed = False
    out = text
    new_out, n = re.subn(r"\n\s*\{\s*\},?\s*(?=\n)", "\n", out)
    if n:
        changed = True
        out = new_out
    # 连续两个 `{` 起头的残片（缺闭合）→ 尽量删到下一个完整路由前
    new_out, n = re.subn(r",\s*\n(\s*)\{(\s*\n\s*)\{", r",\n\1{", out)
    if n:
        changed = True
        out = new_out
    # path: 'quality-management' 仅剩空壳 → 指到仍存在的录入检验
    if "inspection-entry" in out and re.search(
        r"path:\s*['\"]quality-management['\"]\s*,?\s*\n\s*\}", out
    ):
        fixed, n2 = re.subn(
            r"(path:\s*['\"]quality-management['\"]\s*,)\s*\n(\s*)\}",
            r"\1\n\2  redirect: '/quality-management/inspection-entry',\n\2}",
            out,
            count=1,
        )
        if n2:
            changed = True
            out = fixed
    # 压缩多余空行
    compact, n3 = re.subn(r"\n{3,}", "\n\n", out)
    if n3:
        changed = True
        out = compact
    return out, changed


def _js_syntax_ok(text: str) -> bool:
    """粗检：括号平衡 + 无「组件后紧跟 {」这类典型残片。"""
    if not (text or "").strip():
        return False
    if re.search(r"component:\s*\w+\s*,?\s*\n\s*\{", text):
        return False
    depth = 0
    in_str: str | None = None
    escape = False
    for ch in text:
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in {"'", '"', "`"}:
            in_str = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _patch_menu_router(sandbox: Path, target: Path, features: list[str]) -> list[str]:
    patched: list[str] = []
    for rel in _MENU_FILES:
        _ensure_file_in_sandbox(sandbox, target, rel)
        path = sandbox / rel
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = raw
        any_change = False
        for feat in features:
            body, c1 = _strip_menu_lines(body, feat)
            if rel.endswith("router/index.js"):
                body, c2 = _strip_router_blocks(body, feat)
            else:
                c2 = False
            any_change = any_change or c1 or c2
        if any_change and body != raw:
            if rel.endswith("router/index.js") and not _js_syntax_ok(body):
                # 原文本就不完整 / 已删净：落最小合法壳，避免既拦落盘又残留待删标记
                if not body.strip() or not _js_syntax_ok(raw):
                    body = "const routes = []\nexport default routes\n"
                else:
                    # 写坏原本合法的路由会直接导致 Vite 白屏；拒绝落盘
                    continue
            path.write_text(body, encoding="utf-8")
            patched.append(rel)
    return patched


def _strip_main_router_hooks(text: str, modules: list[str]) -> tuple[str, bool]:
    """从 FastAPI main.py 卸掉指定 router 的 import 与 include_router。"""
    if not text or not modules:
        return text, False
    out = text
    changed = False
    for mod in modules:
        m = str(mod or "").strip()
        if not m or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", m):
            continue
        # import 列表中的「mod,」或「mod」单独一行
        new_out, n1 = re.subn(
            rf"(?m)^\s*{re.escape(m)}\s*,\s*\n",
            "",
            out,
        )
        new_out2, n2 = re.subn(
            rf"(?m)^\s*{re.escape(m)}\s*\n",
            "",
            new_out,
        )
        # from .routers import ( ... mod, ... ) 同行残留
        new_out3, n3 = re.subn(
            rf",\s*{re.escape(m)}\b",
            "",
            new_out2,
        )
        new_out4, n4 = re.subn(
            rf"\b{re.escape(m)}\s*,\s*",
            "",
            new_out3,
        )
        # include_router 行
        new_out5, n5 = re.subn(
            rf"(?m)^\s*app\.include_router\(\s*{re.escape(m)}\.router\s*\)\s*\n?",
            "",
            new_out4,
        )
        # 单名 import：from app.routers import kanban_general
        new_out6, n6 = re.subn(
            rf"(?m)^\s*from\s+[\w.]+\s+import\s+{re.escape(m)}\s*\n",
            "",
            new_out5,
        )
        if n1 or n2 or n3 or n4 or n5 or n6:
            changed = True
            out = new_out6
    return out, changed


def _router_mods_from_deleted(deleted: list[str]) -> list[str]:
    """从过程批准并已删的 backend/app/routers/*.py 推导 main.py 模块名。"""
    mods: list[str] = []
    for rel in deleted or []:
        r = str(rel or "").replace("\\", "/").strip().lstrip("./")
        if not r.startswith("backend/app/routers/") or not r.endswith(".py"):
            continue
        stem = Path(r).stem
        if not stem or stem == "__init__" or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", stem):
            continue
        if stem not in mods:
            mods.append(stem)
    return mods


def _patch_backend_hooks(
    sandbox: Path,
    target: Path,
    features: list[str],
    *,
    deleted: list[str] | None = None,
) -> list[str]:
    """删专属后端路由文件后，同步卸掉 main.py 注册，避免启动 ImportError。"""
    mods = _router_mods_from_deleted(list(deleted or []))
    for feat in features:
        for m in _FEATURE_MAIN_ROUTER_MODS.get(feat, ()):
            if m not in mods:
                mods.append(m)
    if not mods:
        return []
    rel = _MAIN_PY_REL
    if not _ensure_file_in_sandbox(sandbox, target, rel):
        return []
    path = sandbox / rel
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    body, changed = _strip_main_router_hooks(raw, mods)
    if not changed or body == raw:
        return []
    path.write_text(body, encoding="utf-8")
    return [rel]


def _rewrite_stale_feature_links(sandbox: Path, target: Path, features: list[str]) -> list[str]:
    """删列表页后，把仍指向旧路由的兄弟页跳转改到保留入口（避免录入检验跳到 404）。"""
    rewrites: dict[str, list[tuple[str, str, str]]] = {
        "检验记录": [
            (
                "frontend/src/views/production/InspectionEntryView.vue",
                "/quality-management/inspection-records",
                "/quality-management/inspection-entry",
            ),
        ],
    }
    patched: list[str] = []
    for feat in features:
        for rel, old, new in rewrites.get(feat, ()):
            if not _ensure_file_in_sandbox(sandbox, target, rel):
                continue
            path = sandbox / rel
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if old not in raw:
                continue
            body = raw.replace(old, new)
            if body == raw:
                continue
            path.write_text(body, encoding="utf-8")
            patched.append(rel)
            tg = target / rel
            try:
                tg.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, tg, follow_symlinks=False)
            except OSError:
                pass
    return patched


def reconcile_delete_artifacts(
    *,
    sandbox: Path,
    target: Path,
    requirement: str,
    assistant_text: str = "",
    explicit_planned: list[str] | None = None,
    sink: Sink | None = None,
) -> dict[str, Any]:
    """
    Cursor 结束后：物理删除页面/API，并修补菜单/路由。
    返回 forced_deletes（须在目标工程删除的路径）、patched（改过的菜单/路由）。
    """
    if not is_delete_intent(requirement):
        return {"forced_deletes": [], "patched": [], "detail": ""}

    def emit(text: str) -> None:
        if sink:
            sink({"type": "status", "text": text})

    features = extract_delete_features(requirement)
    if explicit_planned is not None:
        planned = list(explicit_planned)
    else:
        planned = plan_delete_file_targets(requirement, target)
        claimed = extract_claimed_deleted_paths(assistant_text)
        for rel in claimed:
            rel_n = str(rel or "").replace("\\", "/").strip().lstrip("./")
            if not rel_n or rel_n in planned:
                continue
            if _safe_file_under_root(target, rel_n) is not None:
                planned.append(rel_n)

    forced: list[str] = []
    sandbox = sandbox.resolve()
    target = target.resolve()

    for rel in planned:
        rel_n = rel.replace("\\", "/").lstrip("/")
        if rel_n in _MENU_ROUTER_FILES or _rel_is_protected(rel_n) or is_sensitive_rel(rel_n):
            continue
        if ".." in Path(rel_n).parts:
            continue
        if _safe_file_under_root(target, rel_n) is None and not (sandbox / rel_n).is_file():
            # 目标已无且沙箱也无 → 跳过；沙箱有则仍可删沙箱副本
            if not (sandbox / rel_n).is_file():
                continue
            try:
                (sandbox / rel_n).resolve().relative_to(sandbox.resolve())
            except (OSError, ValueError):
                continue
        sb = sandbox / rel_n
        tg = target / rel_n
        _ensure_file_in_sandbox(sandbox, target, rel_n)
        sb = sandbox / rel_n
        removed = False
        if sb.is_file() and _delete_file(sb):
            removed = True
        if tg.is_file():
            try:
                tg.resolve().relative_to(target)
            except (OSError, ValueError):
                continue
            if _delete_file(tg):
                removed = True
        if removed:
            forced.append(rel_n)
            emit(f"引擎已删除：{rel_n}")

    patched = _patch_menu_router(sandbox, target, features)
    patched.extend(_rewrite_stale_feature_links(sandbox, target, features))
    patched.extend(_patch_backend_hooks(sandbox, target, features, deleted=forced))
    if patched:
        emit("引擎已修补菜单/路由/后端注册：" + "、".join(dict.fromkeys(patched)))
        for rel in patched:
            sb = sandbox / rel
            tg = target / rel
            if sb.is_file():
                try:
                    tg.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sb, tg, follow_symlinks=False)
                except OSError:
                    pass

    detail = ""
    if forced or patched:
        detail = f"引擎强制执行：删除 {len(forced)} 个文件" + (
            f"；修补 {len(list(dict.fromkeys(patched)))} 个接线文件" if patched else ""
        )
    return {"forced_deletes": forced, "patched": list(dict.fromkeys(patched)), "detail": detail}


def build_delete_delivery(
    requirement: str,
    rec: dict[str, Any],
    *,
    target_root: Path | None = None,
) -> str:
    """引擎直删路径的终稿 Markdown。"""
    features = extract_delete_features(requirement)
    feat_label = "、".join(f"「{f}」" for f in features) if features else "目标功能"
    forced = list(rec.get("forced_deletes") or [])
    patched = list(rec.get("patched") or [])
    from .delete_verify import verify_delete_on_target

    ok = True
    if target_root is not None:
        ok = bool(verify_delete_on_target(target_root, requirement).get("ok"))

    lines = [
        "## 说明方案",
        "",
        "**结论**",
        f"已由引擎直接下线 {feat_label}：删除页面/API 文件并修补菜单与路由"
        + ("；本机核对通过。" if ok else "。"),
        "",
        "**改动文件**",
    ]
    if forced:
        for rel in forced:
            lines.append(f"- `{rel}`：已删除")
    if patched:
        for rel in patched:
            lines.append(f"- `{rel}`：已移除菜单/路由引用")
    if not forced and not patched:
        lines.append("- 无：本机已无相关引用或此前已完成")
    lines.extend(
        [
            "",
            "**行为约定**",
            f"- 已删除/下线：{feat_label} 相关菜单、路由、页面与 API",
            "- 保留：同模块其余子功能",
            "- 未改动：其它业务模块",
            "",
        ]
        + _acceptance_lines(label=feat_label)
    )
    return "\n".join(lines) + "\n"


def _acceptance_lines(*, label: str = "", verify_detail: str = "") -> list[str]:
    """删除终稿「验收」四条：面向业务同学，避免路由/404/验尸等术语。"""
    detail = str(verify_detail or "").strip()
    detail = (
        detail.replace("本机工程验尸通过", "")
        .replace("本机工程核对通过", "")
        .replace("验尸通过", "")
        .replace("核对通过", "")
        .lstrip("：:")
        .strip()
    )
    if detail:
        check4 = f"4. 本机代码已核对：{detail}"
    elif label:
        check4 = f"4. 本机代码已核对：{label}相关菜单、页面与路由已清除"
    else:
        check4 = "4. 本机代码已核对：相关菜单、页面与路由已清除"
    return [
        "**验收**",
        "1. 打开系统，在对应模块菜单中确认该项已消失",
        "2. 原先功能页地址不应再进入该功能",
        "3. 同模块其它功能仍可正常使用",
        check4,
    ]


def _change_note_for_rel(rel: str, *, deleted: bool) -> str:
    r = str(rel or "").replace("\\", "/")
    if deleted:
        if r.startswith("frontend/src/views/") or r.endswith(".vue"):
            return "已删除（页面）"
        if "/api/" in r or r.endswith(".js"):
            return "已删除（API 封装）"
        if "/routers/" in r:
            return "已删除（后端路由）"
        return "已删除"
    if r.endswith("AppLayout.vue") or "/layouts/" in r:
        return "已移除相关菜单项"
    if r.endswith("router/index.js") or "/router/" in r:
        return "已移除相关路由项"
    if r.endswith("main.py"):
        return "已卸掉 router 注册（import / include_router）"
    if "schemas" in r:
        return "已清理相关模型段"
    return "已修补接线"


def build_engine_delete_delivery(
    requirement: str,
    *,
    forced_deletes: list[str],
    patched: list[str],
    verify_detail: str = "",
    mode: str = "engine_first",
    process_text: str = "",
) -> str:
    """引擎执行删除后的终稿。改动文件从过程清单对齐实际落盘，不写死功能映射。"""
    features = extract_delete_features(requirement)
    label = "、".join(f"「{f}」" for f in features) if features else "目标功能"
    dels, pats = align_delivery_files_with_process(
        process_text or "",
        deleted=list(forced_deletes or []),
        patched=list(patched or []),
    )
    mode_n = str(mode or "engine_first").strip().lower()
    parts: list[str] = []
    if any(r.endswith(".vue") or "/views/" in r for r in dels):
        parts.append("页面")
    if any("/api/" in r for r in dels):
        parts.append("API")
    if any("/routers/" in r for r in dels):
        parts.append("后端路由")
    if any(r.endswith("main.py") for r in pats):
        parts.append("后端注册")
    if any("layouts/" in r or "/router/" in r or r.endswith("AppLayout.vue") for r in pats):
        parts.append("菜单与前端路由")
    what = "、".join(parts) if parts else "相关入口"
    if mode_n == "cursor_plan":
        intro = (
            f"已由 Cursor 只读定位清单、引擎在本机工程下线{label}："
            f"已处理{what}（改盘仅引擎执行，避免误删与 CRUD 误实现）。"
        )
    elif mode_n == "already_done":
        intro = (
            f"本机代码已核对：{label}相关菜单、页面与路由已清除，"
            "目标状态已达成，本次无需再删文件。"
        )
    else:
        intro = (
            f"已由引擎在本机工程下线{label}："
            f"已处理{what}（未调用 Cursor，避免超时与误实现 CRUD）。"
        )
    lines = [
        "## 说明方案",
        "",
        "**结论**",
        intro,
        "",
        "**改动文件**",
    ]
    if dels:
        for rel in dels:
            lines.append(f"- `{rel}`：{_change_note_for_rel(rel, deleted=True)}")
    if pats:
        for rel in pats:
            lines.append(f"- `{rel}`：{_change_note_for_rel(rel, deleted=False)}")
    if not dels and not pats:
        lines.append("- 无额外 diff：本机已无相关入口或此前已完成")
    lines.extend(
        [
            "",
            "**行为约定**",
            f"- 已下线：{label} 相关菜单、路由、页面与 API",
            "- 保留：同模块其余子功能",
            "- 未改动：其它业务模块",
            "",
        ]
    )
    lines.extend(_acceptance_lines(label=label, verify_detail=verify_detail))
    if mode_n == "already_done":
        from .delete_verify import runtime_hint_always

        hint = runtime_hint_always()
        if hint:
            lines.extend(["", hint])
    return "\n".join(lines) + "\n"
