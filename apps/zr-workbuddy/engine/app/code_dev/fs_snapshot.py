"""沙箱文件快照：Cursor 本地 Agent 写完后对比变更（不依赖 LLM write_file 记账）。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .config import COPY_SKIP_DIR_NAMES, SENSITIVE_BASENAMES, SENSITIVE_PATH_PARTS, SENSITIVE_SUFFIXES
from .sandbox import is_sensitive_rel


def _skip_dirname(name: str) -> bool:
    if name in COPY_SKIP_DIR_NAMES or name.startswith(".git"):
        return True
    # Cursor / 编辑器本地状态，勿当业务变更同步回目标工程
    if name in {".cursor", ".cursor-tutor", ".cursor-sdk-store", ".idea", ".vscode"}:
        return True
    return False


def _should_skip_rel(rel: str) -> bool:
    if not rel or is_sensitive_rel(rel):
        return True
    parts = Path(rel.replace("\\", "/")).parts
    for part in parts:
        if _skip_dirname(part):
            return True
        if part in SENSITIVE_PATH_PARTS or part in SENSITIVE_BASENAMES:
            return True
        lower = part.lower()
        if any(lower.endswith(suf) for suf in SENSITIVE_SUFFIXES):
            return True
    return False


def _file_fingerprint(path: Path) -> str:
    """小文件内容哈希；大文件用 size+mtime，避免读爆。"""
    try:
        st = path.stat()
    except OSError:
        return ""
    size = int(st.st_size)
    if size <= 256_000:
        try:
            h = hashlib.sha256()
            with path.open("rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            return f"h:{h.hexdigest()}"
        except OSError:
            pass
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
    return f"m:{size}:{mtime_ns}"


def snapshot_sandbox(sandbox: Path) -> dict[str, str]:
    """返回 rel_posix → fingerprint。"""
    root = Path(sandbox).resolve()
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        # 原地过滤
        keep: list[str] = []
        for d in list(dirnames):
            if _skip_dirname(d):
                continue
            keep.append(d)
        dirnames[:] = keep
        base = Path(dirpath)
        for name in filenames:
            path = base / name
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if _should_skip_rel(rel):
                continue
            # 不把符号链接算进变更（避免链出沙箱的文件被列入同步清单）
            if path.is_symlink() or not path.is_file():
                continue
            fp = _file_fingerprint(path)
            if fp:
                out[rel] = fp
    return out


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """新增或内容变化的相对路径（不含仅删除）。"""
    changed: list[str] = []
    for rel, fp in after.items():
        if before.get(rel) != fp:
            changed.append(rel)
    changed.sort()
    return changed
