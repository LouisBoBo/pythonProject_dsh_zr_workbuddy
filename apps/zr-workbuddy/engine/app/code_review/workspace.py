"""审码目标路径校验（只读，不要求可写）。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..code_dev.workspace import detect_project_markers, normalize_workspace
from .config import ALLOWED_SUFFIXES


def _forbidden_reason(root: Path) -> str | None:
    from ..code_dev.workspace import _is_forbidden_target

    return _is_forbidden_target(root)


def validate_review_root(path: str) -> dict[str, Any]:
    """返回 {ok, path, exists, readable, is_file, looks_like_project, project_markers, error}。"""
    base: dict[str, Any] = {
        "ok": False,
        "path": (path or "").strip(),
        "exists": False,
        "readable": False,
        "is_file": False,
        "looks_like_project": False,
        "project_markers": [],
        "error": "",
    }
    try:
        p = normalize_workspace(path)
    except ValueError as e:
        base["error"] = str(e)
        return base

    base["path"] = str(p)
    bad = _forbidden_reason(p)
    if bad:
        base["exists"] = p.exists()
        base["error"] = bad
        return base

    if not p.exists():
        base["error"] = "路径不存在"
        return base

    if p.is_file():
        if p.suffix.lower() not in ALLOWED_SUFFIXES:
            base["error"] = f"不支持审阅该文件类型：{p.suffix}"
            return base
        if not os.access(p, os.R_OK):
            base["error"] = "文件不可读"
            return base
        base["exists"] = True
        base["readable"] = True
        base["is_file"] = True
        base["ok"] = True
        return base

    if not p.is_dir():
        base["error"] = "路径既不是目录也不是支持的源码文件"
        return base
    if not os.access(p, os.R_OK | os.X_OK):
        base["error"] = "目录不可读"
        return base

    base["exists"] = True
    base["readable"] = True
    markers = detect_project_markers(p)
    base["project_markers"] = markers
    base["looks_like_project"] = len(markers) > 0
    base["ok"] = True
    if not markers:
        base["error"] = ""
        base["note"] = "未检测到典型工程标记，仍可审阅指定子路径或文件"
    return base


def resolve_scope_root(root: Path, scope: str) -> tuple[Path | None, str | None]:
    """scope 为相对子路径，须落在 root 内。"""
    raw = (scope or "").strip().replace("\\", "/").strip("/")
    if not raw:
        return root, None
    if raw.startswith("~") or raw.startswith("/"):
        return None, "scope 须为相对路径"
    target = (root / raw).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None, "scope 超出工程根目录"
    if not target.exists():
        return None, f"scope 路径不存在：{raw}"
    return target, None
