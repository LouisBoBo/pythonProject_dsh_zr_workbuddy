"""目录沙箱：创建、受限拷贝、闸门、同步到目标。"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

from .config import (
    COPY_SKIP_DIR_NAMES,
    CodeDevConfig,
    SENSITIVE_BASENAMES,
    SENSITIVE_PATH_PARTS,
    SENSITIVE_SUFFIXES,
    get_config,
)


def sandboxes_dir(data_dir: Path) -> Path:
    d = Path(data_dir) / "local_dev" / "sandboxes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sandbox_root(data_dir: Path, job_id: str) -> Path:
    safe = "".join(c for c in job_id if c.isalnum() or c in "-_")
    if not safe or safe != job_id:
        raise ValueError("invalid job_id")
    root = sandboxes_dir(data_dir) / safe
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def is_sensitive_rel(rel: str) -> bool:
    parts = Path(rel.replace("\\", "/")).parts
    if not parts:
        return False
    for part in parts:
        if part in SENSITIVE_PATH_PARTS:
            return True
        if part in SENSITIVE_BASENAMES:
            return True
        lower = part.lower()
        if any(lower.endswith(suf) for suf in SENSITIVE_SUFFIXES):
            return True
    return False


def _should_skip_dirname(name: str, rel_dir: Path) -> bool:
    """目录过滤：标准跳过名 + engine/data 运行时目录。"""
    if name in COPY_SKIP_DIR_NAMES or name.startswith(".git"):
        return True
    # apps/.../engine/data：Job/沙箱/日志，整仓拷会轻易爆 4000
    parent = rel_dir.name if str(rel_dir) != "." else ""
    if name == "data" and parent == "engine":
        return True
    parts = rel_dir.parts + (name,)
    if len(parts) >= 2 and parts[-1] == "data" and parts[-2] == "engine":
        return True
    return False


def _copy_one_file(
    src: Path,
    dest: Path,
    *,
    cfg: CodeDevConfig,
    total_bytes: int,
) -> tuple[bool, int]:
    """拷贝单个普通文件；返回 (是否计入, 新 total_bytes)。"""
    if src.is_symlink() or not src.is_file():
        return False, total_bytes
    try:
        size = src.stat().st_size
    except OSError:
        return False, total_bytes
    if size > cfg.max_file_bytes:
        return False, total_bytes
    if total_bytes + size > cfg.copy_max_total_bytes:
        raise RuntimeError("工程体积过大，无法完整拷入沙箱")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dest, follow_symlinks=False)
    except OSError:
        return False, total_bytes
    if dest.is_symlink():
        try:
            dest.unlink()
        except OSError:
            pass
        return False, total_bytes
    return True, total_bytes + size


def _prepare_sandbox_sparse(
    root: Path,
    target_workspace: Path,
    include_rels: list[str],
    *,
    cfg: CodeDevConfig,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """仅拷贝 write_scope / 门禁 findings 相关路径（及 Python 包 __init__ 链）。"""
    from .path_scope import normalize_write_scope

    scope = normalize_write_scope(include_rels)
    if not scope:
        raise RuntimeError("稀疏拷贝范围为空")

    if on_progress:
        on_progress(f"按写范围稀疏拷贝沙箱（{len(scope)} 条路径）…")

    # 扩展：目录范围 + 文件 + 祖先 __init__.py（便于 import）
    planned: list[str] = []
    seen: set[str] = set()

    def add_rel(rel: str) -> None:
        r = (rel or "").replace("\\", "/").strip().lstrip("./")
        if not r or r in seen or is_sensitive_rel(r):
            return
        seen.add(r)
        planned.append(r)

    for item in scope:
        raw = item.replace("\\", "/").strip().lstrip("./")
        if not raw:
            continue
        if raw.endswith("/"):
            sub = target_workspace / raw.rstrip("/")
            if sub.is_dir():
                for dirpath, dirnames, filenames in os_walk_filtered(sub):
                    rel_dir = Path(dirpath).relative_to(target_workspace)
                    dirnames[:] = [
                        d for d in list(dirnames) if not _should_skip_dirname(d, rel_dir)
                    ]
                    for name in filenames:
                        rel = str(
                            (rel_dir / name).as_posix() if str(rel_dir) != "." else name
                        )
                        add_rel(rel)
            continue
        add_rel(raw)
        # 祖先包初始化文件
        parent = Path(raw).parent
        while str(parent) not in {".", ""}:
            add_rel(str((parent / "__init__.py").as_posix()))
            parent = parent.parent

    copied = 0
    total_bytes = 0
    missing: list[str] = []
    for rel in planned:
        if copied >= cfg.copy_max_files:
            raise RuntimeError(
                f"稀疏拷贝仍超过上限（>{cfg.copy_max_files}），请缩小 write_scope"
            )
        src = target_workspace / rel
        if not src.is_file():
            if Path(rel).name == "__init__.py":
                continue
            missing.append(rel)
            continue
        ok, total_bytes = _copy_one_file(src, root / rel, cfg=cfg, total_bytes=total_bytes)
        if ok:
            copied += 1

    if copied == 0:
        sample = "、".join(missing[:5]) or "（无有效文件）"
        raise RuntimeError(f"稀疏拷贝未找到可写文件：{sample}")

    if on_progress:
        on_progress(f"稀疏沙箱就绪：{copied} 个文件" + (f"（缺 {len(missing)}）" if missing else ""))
    return {
        "sandbox": str(root),
        "copied_files": copied,
        "skipped_dir_hits": 0,
        "mode": "sparse",
        "total_bytes": total_bytes,
        "include_rels": planned[:80],
        "missing_rels": missing[:20],
    }


def prepare_sandbox(
    data_dir: Path,
    job_id: str,
    target_workspace: Path,
    *,
    empty_target: bool,
    cfg: CodeDevConfig | None = None,
    on_progress: Callable[[str], None] | None = None,
    include_rels: list[str] | None = None,
) -> dict[str, Any]:
    """创建沙箱：空目标 → 空仓；有 include_rels → 稀疏拷贝；否则受限全量拷贝。"""
    cfg = cfg or get_config()
    root = sandbox_root(data_dir, job_id)
    # 清空旧内容
    if root.exists():
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
    root.mkdir(parents=True, exist_ok=True)

    if empty_target:
        if on_progress:
            on_progress("沙箱已就绪（空项目）")
        return {"sandbox": str(root), "copied_files": 0, "mode": "empty"}

    scoped = [str(p).strip() for p in (include_rels or []) if str(p).strip()]
    if scoped:
        return _prepare_sandbox_sparse(
            root,
            target_workspace,
            scoped,
            cfg=cfg,
            on_progress=on_progress,
        )

    copied = 0
    total_bytes = 0
    skipped_dirs = 0
    if on_progress:
        on_progress("正在将目标工程受限拷贝到沙箱…")

    for dirpath, dirnames, filenames in os_walk_filtered(target_workspace):
        rel_dir = Path(dirpath).relative_to(target_workspace)
        keep: list[str] = []
        for d in list(dirnames):
            if _should_skip_dirname(d, rel_dir):
                skipped_dirs += 1
                continue
            keep.append(d)
        dirnames[:] = keep

        dest_dir = root / rel_dir if str(rel_dir) != "." else root
        dest_dir.mkdir(parents=True, exist_ok=True)

        for name in filenames:
            if copied >= cfg.copy_max_files:
                raise RuntimeError(
                    f"工程文件过多（>{cfg.copy_max_files}）。"
                    "请缩小工程目录、排除依赖/运行时 data，"
                    "或对门禁修复等任务使用带 write_scope 的稀疏拷贝后再试"
                )
            src = Path(dirpath) / name
            rel = str((rel_dir / name).as_posix() if str(rel_dir) != "." else name)
            if is_sensitive_rel(rel):
                continue
            ok, total_bytes = _copy_one_file(
                src, root / rel, cfg=cfg, total_bytes=total_bytes
            )
            if ok:
                copied += 1

    if on_progress:
        on_progress(f"沙箱拷贝完成：{copied} 个文件")
    return {
        "sandbox": str(root),
        "copied_files": copied,
        "skipped_dir_hits": skipped_dirs,
        "mode": "copy",
        "total_bytes": total_bytes,
    }


def os_walk_filtered(root: Path):
    import os

    yield from os.walk(root)


def resolve_in_sandbox(sandbox: Path, rel: str) -> Path:
    """相对路径解析到沙箱内；防 ../ 逃逸。"""
    raw = (rel or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("~"):
        raise ValueError("只允许沙箱内相对路径")
    if ".." in Path(raw).parts:
        raise ValueError("路径不允许包含 ..")
    target = (sandbox / raw).resolve()
    root = sandbox.resolve()
    try:
        target.relative_to(root)
    except ValueError as e:
        raise ValueError("路径逃逸出沙箱") from e
    return target


def sandbox_entry(sandbox: Path, rel: str) -> Path:
    """沙箱内未 resolve 的入口路径（用于检测符号链接）；同样拒绝 .. / 绝对路径。"""
    raw = (rel or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("~"):
        raise ValueError("只允许沙箱内相对路径")
    if ".." in Path(raw).parts:
        raise ValueError("路径不允许包含 ..")
    entry = sandbox / raw
    if entry.is_symlink():
        return entry
    root = sandbox.resolve()
    try:
        entry.resolve(strict=False).relative_to(root)
    except ValueError as e:
        raise ValueError("路径逃逸出沙箱") from e
    return entry


def resolve_regular_file_in_sandbox(sandbox: Path, rel: str) -> Path:
    """仅允许沙箱内普通文件；符号链接一律拒绝（防链出宿主机敏感文件）。"""
    entry = sandbox_entry(sandbox, rel)
    if entry.is_symlink():
        raise ValueError("拒绝符号链接")
    if not entry.exists():
        raise FileNotFoundError(rel)
    if not entry.is_file():
        raise ValueError("不是普通文件")
    return resolve_in_sandbox(sandbox, rel)


def sync_changed_to_target(
    sandbox: Path,
    target: Path,
    changed_rels: list[str],
    *,
    cfg: CodeDevConfig | None = None,
) -> list[str]:
    """将变更相对路径从沙箱同步到目标；返回实际写入列表。

    - 先校验再写入；单文件先写临时文件再 replace，降低半截文件风险
    - 拒绝符号链接与逃逸路径（跳过该项，不拖垮整次同步中的合法文件）
    - 应同步却缺失的非敏感普通文件会抛错，避免静默丢变更
    """
    import os

    cfg = cfg or get_config()
    sandbox = sandbox.resolve()
    target = target.resolve()
    if not target.is_dir():
        raise RuntimeError("目标目录无效")

    requested: list[str] = []
    for rel in changed_rels:
        rel_n = str(rel or "").strip().replace("\\", "/")
        if not rel_n or is_sensitive_rel(rel_n):
            continue
        requested.append(rel_n)

    planned: list[tuple[str, Path, Path]] = []
    missing: list[str] = []
    skipped_unsafe: list[str] = []
    total_bytes = 0
    for rel_n in requested:
        try:
            src = resolve_regular_file_in_sandbox(sandbox, rel_n)
        except FileNotFoundError:
            missing.append(rel_n)
            continue
        except ValueError:
            skipped_unsafe.append(rel_n)
            continue
        size = src.stat().st_size
        if size > cfg.max_file_bytes:
            raise RuntimeError(f"文件过大，拒绝同步：{rel_n}")
        if total_bytes + size > cfg.max_total_write_bytes:
            raise RuntimeError(
                f"本任务同步字节超限（>{cfg.max_total_write_bytes}），已中止"
            )
        dest = (target / rel_n).resolve()
        try:
            dest.relative_to(target)
        except ValueError as e:
            raise RuntimeError(f"同步路径逃逸：{rel_n}") from e
        # 目标若已是指向沙箱外的符号链接，拒绝覆盖写穿
        dest_entry = target / rel_n
        if dest_entry.is_symlink():
            try:
                dest_entry.resolve().relative_to(target)
            except ValueError as e:
                raise RuntimeError(f"目标路径为外链，拒绝覆盖：{rel_n}") from e
        planned.append((rel_n, src, dest))
        total_bytes += size

    if missing:
        sample = "、".join(missing[:5])
        more = f" 等 {len(missing)} 个" if len(missing) > 5 else ""
        raise RuntimeError(f"沙箱中缺少待同步文件：{sample}{more}")

    if not planned:
        if skipped_unsafe:
            sample = "、".join(skipped_unsafe[:5])
            raise RuntimeError(
                f"没有可同步的安全文件（已跳过符号链接/逃逸路径：{sample}）"
            )
        raise RuntimeError("没有可同步的有效文件")

    written: list[str] = []
    for rel_n, src, dest in planned:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".wb-sync-tmp")
        try:
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            shutil.copy2(src, tmp, follow_symlinks=False)
            if tmp.is_symlink():
                tmp.unlink()
                raise RuntimeError(f"同步产生符号链接，已拒绝：{rel_n}")
            os.replace(tmp, dest)
        except OSError as e:
            try:
                if tmp.exists() or tmp.is_symlink():
                    tmp.unlink()
            except OSError:
                pass
            raise RuntimeError(f"同步写入失败：{rel_n}（{e}）") from e
        written.append(rel_n)

    if len(written) != len(planned):
        raise RuntimeError(
            f"同步不完整：计划 {len(planned)} 个，实际 {len(written)} 个"
        )
    return written
