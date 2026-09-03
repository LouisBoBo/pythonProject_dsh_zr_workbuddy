"""Git diff → 受影响部署单元。"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .units import DeployUnit, map_paths_to_units


def _run_git(cwd: Path, *args: str, timeout: int = 60) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def list_changed_paths(
    workspace: Path | str,
    *,
    base_ref: str,
    head_ref: str = "HEAD",
) -> dict[str, Any]:
    """列出 base..head 变更路径；base 无效时回落为空并带 error。"""
    import re

    root = Path(workspace).expanduser().resolve()
    base = (base_ref or "").strip() or "HEAD~1"
    head = (head_ref or "").strip() or "HEAD"
    # 拒绝 range 语法与壳层危险字符；允许 HEAD、SHA、branch、HEAD~1、tags/x
    _REF_OK = re.compile(r"^[A-Za-z0-9._/\-]+(?:[~^][0-9]*)?$")
    if ".." in base or ".." in head:
        return {"ok": False, "paths": [], "error": "非法 git ref"}
    if not _REF_OK.match(base) or not _REF_OK.match(head):
        return {"ok": False, "paths": [], "error": "非法 git ref 字符"}
    # 确认是 git 仓
    code, _, err = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        return {"ok": False, "paths": [], "error": err or "不是 git 仓库"}
    code_b, base_sha, err_b = _run_git(root, "rev-parse", "--verify", base)
    if code_b != 0:
        # 尝试 origin/HEAD 或空树
        code2, out2, _ = _run_git(root, "rev-list", "--max-parents=0", "HEAD")
        if code2 == 0 and (out2 or "").strip():
            base = (out2 or "").splitlines()[0].strip()
            code_b, base_sha, err_b = _run_git(root, "rev-parse", "--verify", base)
        if code_b != 0:
            return {
                "ok": False,
                "paths": [],
                "error": f"无法解析 base_ref={base_ref!r}：{err_b or err}",
                "base_ref": base_ref,
                "head_ref": head,
            }
    code_h, head_sha, err_h = _run_git(root, "rev-parse", "--verify", head)
    if code_h != 0:
        return {"ok": False, "paths": [], "error": err_h or f"无法解析 head={head}"}
    code_d, out_d, err_d = _run_git(
        root, "diff", "--name-only", f"{base_sha.strip()}..{head_sha.strip()}"
    )
    if code_d != 0:
        return {"ok": False, "paths": [], "error": err_d or "git diff 失败"}
    paths = []
    for line in (out_d or "").splitlines():
        p = line.strip().replace("\\", "/")
        if p:
            paths.append(p)
    return {
        "ok": True,
        "paths": paths,
        "base_ref": base,
        "base_sha": base_sha.strip(),
        "head_ref": head,
        "head_sha": head_sha.strip(),
        "error": "",
    }


def list_dirty_paths(workspace: Path | str) -> dict[str, Any]:
    """工作区未提交路径（含未跟踪），供策略纳入对比。"""
    root = Path(workspace).expanduser().resolve()
    code, out, err = _run_git(root, "status", "--porcelain", "-u")
    if code != 0:
        return {"ok": False, "paths": [], "error": err or "git status 失败"}
    paths: list[str] = []
    for line in (out or "").splitlines():
        if len(line) < 4:
            continue
        # XY PATH or XY ORIG -> PATH
        rest = line[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[-1].strip()
        # quoted paths
        if rest.startswith('"') and rest.endswith('"'):
            rest = rest[1:-1]
        p = rest.replace("\\", "/").strip()
        if p:
            paths.append(p)
    return {"ok": True, "paths": paths, "error": ""}


def units_from_diff(
    workspace: Path | str,
    *,
    base_ref: str,
    head_ref: str = "HEAD",
    include_dirty: bool = True,
) -> dict[str, Any]:
    diff = list_changed_paths(workspace, base_ref=base_ref, head_ref=head_ref)
    if not diff.get("ok"):
        return {**diff, "units": [], "skipped_paths": [], "dirty_paths": []}
    paths = list(diff.get("paths") or [])
    dirty_paths: list[str] = []
    if include_dirty:
        dirty = list_dirty_paths(workspace)
        if dirty.get("ok"):
            dirty_paths = list(dirty.get("paths") or [])
            for p in dirty_paths:
                if p not in paths:
                    paths.append(p)
    units = map_paths_to_units(paths)
    skipped = []
    from .units import path_to_unit_id

    for p in paths:
        if path_to_unit_id(p) is None:
            skipped.append(p)
    return {
        **diff,
        "paths": paths,
        "dirty_paths": dirty_paths,
        "units": [u.to_dict() for u in units],
        "unit_objs": units,
        "skipped_paths": skipped[:80],
        "skipped_total": len(skipped),
        "base_resolved": True,
    }


def resolve_units_from_ids(unit_ids: list[str]) -> list[DeployUnit]:
    from .units import build_unit

    out: list[DeployUnit] = []
    seen: set[str] = set()
    for uid in unit_ids:
        u = build_unit(str(uid).strip(), selected=True)
        if u and u.id not in seen:
            seen.add(u.id)
            out.append(u)
    return out
