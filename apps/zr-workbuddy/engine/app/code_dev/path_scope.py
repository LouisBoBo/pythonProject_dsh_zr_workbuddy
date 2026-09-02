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


def partition_by_scope(
    changed_rels: list[str],
    scope: list[str] | None,
) -> tuple[list[str], list[str]]:
    """返回 (in_scope, out_of_scope)。"""
    scope_n = normalize_write_scope(scope)
    if not scope_n:
        cleaned = [normalize_rel(r) for r in changed_rels]
        cleaned = [r for r in cleaned if r]
        return cleaned, []
    inside: list[str] = []
    outside: list[str] = []
    for rel in changed_rels:
        rel_n = normalize_rel(rel)
        if not rel_n:
            continue
        if path_in_scope(rel_n, scope_n):
            inside.append(rel_n)
        else:
            outside.append(rel_n)
    return inside, outside


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
