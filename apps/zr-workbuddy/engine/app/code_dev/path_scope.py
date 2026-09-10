"""本机写码写范围：选定相对路径（文件或目录前缀）后限制同步。

空列表 = 不限制（兼容旧行为，整仓可同步）。
目录项须以 ``/`` 结尾才按前缀匹配；不带尾斜杠仅精确匹配文件。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def normalize_rel(rel: str) -> str:
    text = str(rel or "").strip().replace("\\", "/")
    # 拒绝空字节 / 盘符 / home 简写，降低跨平台路径怪异面
    if not text or "\x00" in text or "~" in text or ":" in text:
        return ""
    while text.startswith("./"):
        text = text[2:]
    text = text.lstrip("/")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return ""
    if len(parts) > 64 or len(text) > 512:
        return ""
    return "/".join(parts)


def normalize_write_scope(raw: list[str] | None, *, max_items: int = 200) -> list[str]:
    """归一化用户勾选；去重保序；非法项丢弃。

    目录须带尾 ``/``（前端勾选文件夹时会带）；不带尾斜杠仅精确匹配该文件，
    避免 ``src`` 误匹配 ``src2/...`` 之外、更关键的是避免把文件名当目录前缀。
    """
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        raw_s = str(item or "").strip().replace("\\", "/")
        want_dir = raw_s.endswith("/")
        rel = normalize_rel(raw_s)
        if not rel:
            continue
        key = rel + ("/" if want_dir else "")
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= max_items:
            break
    return out


def path_in_scope(rel: str, scope: list[str] | None) -> bool:
    """rel 是否落在 scope 内。scope 空 = 全部允许。"""
    scope_n = normalize_write_scope(scope)
    if not scope_n:
        return True
    rel_n = normalize_rel(rel)
    if not rel_n:
        return False
    for allowed in scope_n:
        if allowed.endswith("/"):
            prefix = allowed.rstrip("/")
            if not prefix:
                continue
            if rel_n == prefix or rel_n.startswith(prefix + "/"):
                return True
            continue
        # 文件：仅精确匹配，禁止 ``app`` 吞掉 ``app/x``
        if rel_n == allowed:
            return True
    return False


def is_ui_shell_wiring(rel: str) -> bool:
    """菜单/路由/API/schema 等接线文件：不同步则「写完了但刷新看不到」。

    含 ``frontend/src/config/``（如 reportFeatures.js）：本仓报表侧栏是否显示
    只看 catalog 的 menu 开关；只同步 views/api 而 deferred 掉 config，会反复出现
    「交付说已上菜单、浏览器却没有」。
    """
    rel_n = normalize_rel(rel)
    if not rel_n:
        return False
    if rel_n.startswith("frontend/src/router/"):
        return True
    if rel_n.startswith("frontend/src/layouts/"):
        return True
    if rel_n.startswith("frontend/src/api/"):
        return True
    if rel_n.startswith("frontend/src/config/"):
        return True
    # 少数工程把菜单注册表放在 constants / composables
    name_l = rel_n.rsplit("/", 1)[-1].lower()
    if any(
        rel_n.startswith(p)
        for p in (
            "frontend/src/constants/",
            "frontend/src/composables/",
            "frontend/src/utils/",
        )
    ) and (
        "feature" in name_l
        or name_l.endswith("menu.js")
        or name_l.endswith("menu.ts")
        or ("nav" in name_l and ("menu" in name_l or "route" in name_l))
    ):
        return True
    if rel_n.startswith("backend/app/routers/"):
        return True
    name = rel_n.rsplit("/", 1)[-1]
    if rel_n.startswith("backend/app/") and (
        name.startswith("schemas")
        or name.endswith("_store.py")
        or "schema" in name
        or name.endswith("_store.js")
    ):
        return True
    return False


def is_ui_page_asset(rel: str) -> bool:
    """页面/组件资产：路由已引用时若不同步会直接 Vite 报错。"""
    rel_n = normalize_rel(rel)
    if not rel_n:
        return False
    return rel_n.startswith(
        (
            "frontend/src/views/",
            "frontend/src/components/",
            "frontend/src/pages/",
            "frontend/src/stores/",
            "frontend/src/store/",
        )
    )


def is_backend_feature_asset(rel: str) -> bool:
    """与菜单页配套的后端文件（store/schema/router）。"""
    rel_n = normalize_rel(rel)
    if not rel_n or not rel_n.startswith("backend/app/"):
        return False
    if rel_n.startswith("backend/app/routers/"):
        return True
    name = rel_n.rsplit("/", 1)[-1]
    return (
        name.endswith("_store.py")
        or name.startswith("schemas")
        or "schema" in name
        or "/models/" in ("/" + rel_n + "/")
    )


def _extract_local_import_rels(source_rel: str, text: str) -> list[str]:
    """从 JS/TS/Vue/Python 源码里抽出相对本文件的本地 import 目标（归一成仓库相对路径）。"""
    import re

    src = normalize_rel(source_rel)
    if not src or not text:
        return []
    parent = "/".join(src.split("/")[:-1])
    found: list[str] = []
    def _expand_cands(cand: str) -> None:
        cand = cand.split("?", 1)[0].split("#", 1)[0]
        if not cand:
            return
        found.append(cand)
        if not cand.rsplit("/", 1)[-1].count("."):
            for ext in (".vue", ".js", ".ts", ".tsx", ".jsx"):
                found.append(cand + ext)
            found.append(cand + "/index.js")
            found.append(cand + "/index.ts")
            found.append(cand + "/index.vue")

    # JS/TS/Vue: from '...'; import '...'; require('...')
    for m in re.finditer(
        r"""(?:from|import|require\()\s*['"](\.\.?/[^'"]+)['"]""",
        text,
    ):
        raw = m.group(1).replace("\\", "/")
        # resolve relative to parent
        base_parts = parent.split("/") if parent else []
        for part in raw.split("/"):
            if part == "." or part == "":
                continue
            if part == "..":
                if base_parts:
                    base_parts.pop()
                continue
            base_parts.append(part)
        _expand_cands("/".join(base_parts))
    # Vue/Vite 常见别名：@/ → frontend/src/（若源文件在 frontend 下）
    src_root = "frontend/src"
    if src.startswith("frontend/"):
        src_root = "frontend/src"
    elif src.startswith("src/"):
        src_root = "src"
    for m in re.finditer(
        r"""(?:from|import|require\()\s*['"](@/[^'"]+|~/[^'"]+)['"]""",
        text,
    ):
        raw = m.group(1).replace("\\", "/")
        if raw.startswith("@/"):
            _expand_cands(src_root + "/" + raw[2:])
        elif raw.startswith("~/"):
            _expand_cands(src_root + "/" + raw[2:])
    # Python: from .x import / from ..pkg import — skip complex; routers already covered
    return [normalize_rel(x) for x in found if normalize_rel(x)]


def promote_shell_companions(
    inside: list[str],
    outside: list[str],
    *,
    changed_all: list[str] | None = None,
    sandbox_root: Path | None = None,
) -> tuple[list[str], list[str]]:
    """路由/布局已进同步集时，强制带上同批变更的页面与后端配套，并按 import 闭包再扩一轮。

    典型故障：write_scope 误判为 production/，warehouse 视图进 deferred，
    但 router 已同步 → Vite Failed to resolve import。
    """
    in_set = [normalize_rel(r) for r in inside if normalize_rel(r)]
    out_set = [normalize_rel(r) for r in outside if normalize_rel(r)]
    all_changed = {
        normalize_rel(r)
        for r in (changed_all or (in_set + out_set))
        if normalize_rel(r)
    }

    shell_touched = any(is_ui_shell_wiring(r) for r in all_changed) or any(
        is_ui_shell_wiring(r) for r in in_set
    )
    # 仅改了业务页、未改路由时：只把同批 config（菜单开关）拉进同步。
    # 禁止「任意 view 触发 → 把 outside 里其它模块 views 一并同步」（越权写盘）。
    page_touched = any(is_ui_page_asset(r) for r in all_changed) or any(
        is_ui_page_asset(r) for r in in_set
    )
    if shell_touched:
        keep_out: list[str] = []
        for rel in out_set:
            if is_ui_page_asset(rel) or is_backend_feature_asset(rel) or is_ui_shell_wiring(rel):
                if rel not in in_set:
                    in_set.append(rel)
            else:
                keep_out.append(rel)
        out_set = keep_out
    elif page_touched and out_set:
        keep_out = []
        for rel in out_set:
            if rel.startswith("frontend/src/config/"):
                if rel not in in_set:
                    in_set.append(rel)
            else:
                keep_out.append(rel)
        out_set = keep_out

    # import 闭包：已同步文件若引用同批 deferred 文件，一并提升
    if sandbox_root is not None and out_set:
        out_lookup = set(out_set)
        promoted: set[str] = set()
        for rel in list(in_set):
            path = sandbox_root / rel
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for dep in _extract_local_import_rels(rel, text):
                if dep in out_lookup:
                    promoted.add(dep)
        if promoted:
            out_set = [r for r in out_set if r not in promoted]
            for r in sorted(promoted):
                if r not in in_set:
                    in_set.append(r)

    return in_set, out_set


def partition_by_scope(
    changed_rels: list[str],
    scope: list[str] | None,
    *,
    sandbox_root: Path | None = None,
) -> tuple[list[str], list[str]]:
    """返回 (in_scope, out_of_scope)。

    即使 write_scope 较窄，UI 接线文件（路由/布局/api/schema）仍算 in_scope；
    若本批改动触及接线文件，同批 views/components 与后端配套一并强制同步。
    """
    scope_n = normalize_write_scope(scope)
    cleaned = [normalize_rel(r) for r in changed_rels]
    cleaned = [r for r in cleaned if r]
    if not scope_n:
        return cleaned, []
    inside: list[str] = []
    outside: list[str] = []
    for rel_n in cleaned:
        if path_in_scope(rel_n, scope_n) or is_ui_shell_wiring(rel_n):
            inside.append(rel_n)
        else:
            outside.append(rel_n)
    return promote_shell_companions(
        inside,
        outside,
        changed_all=cleaned,
        sandbox_root=sandbox_root,
    )


def list_workspace_entries(
    workspace: Path,
    *,
    subdir: str = "",
    max_entries: int = 400,
) -> dict[str, Any]:
    """列出工程下一级目录项（供前端下钻）。

    返回 rel 相对 workspace；不跟随符号链接；跳过敏感/隐藏常见项。
    """
    from .sandbox import is_sensitive_rel

    root = workspace.resolve()
    if not root.is_dir():
        return {"ok": False, "error": "工程目录无效", "entries": [], "cwd": ""}

    sub = normalize_rel(subdir)
    if subdir and not sub and str(subdir or "").strip():
        return {"ok": False, "error": "子目录路径非法", "entries": [], "cwd": ""}
    if sub.count("/") >= 48:
        return {"ok": False, "error": "目录层级过深", "entries": [], "cwd": ""}
    cur = (root / sub).resolve() if sub else root
    try:
        cur.relative_to(root)
    except ValueError:
        return {"ok": False, "error": "路径越界", "entries": [], "cwd": ""}
    if not cur.is_dir() or cur.is_symlink():
        return {"ok": False, "error": "不是可浏览目录", "entries": [], "cwd": sub}

    skip_names = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        ".turbo",
        "coverage",
    }
    entries: list[dict[str, Any]] = []
    try:
        children = sorted(cur.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        return {"ok": False, "error": f"无法读取目录：{e}", "entries": [], "cwd": sub}

    for child in children:
        name = child.name
        if name in skip_names or name.startswith("."):
            continue
        if child.is_symlink():
            continue
        rel = f"{sub}/{name}" if sub else name
        rel = normalize_rel(rel)
        if not rel or is_sensitive_rel(rel):
            continue
        is_dir = child.is_dir()
        entries.append(
            {
                "name": name,
                "rel": rel + ("/" if is_dir else ""),
                "kind": "dir" if is_dir else "file",
            }
        )
        if len(entries) >= max_entries:
            break

    return {
        "ok": True,
        "error": "",
        "cwd": sub,
        "parent": "/".join(sub.split("/")[:-1]) if sub else None,
        "entries": entries,
    }
