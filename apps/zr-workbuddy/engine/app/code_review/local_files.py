"""本机直读：列表、限流读、敏感路径守卫（无 Git / 无 IDE Bridge）。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..code_dev.sandbox import is_sensitive_rel
from .config import ALLOWED_SUFFIXES, DOC_OR_STYLE_SUFFIXES, SKIP_DIR_NAMES, CodeReviewConfig


def _is_skippable_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.startswith(".")


def _is_vendor_or_minified(rel: str) -> bool:
    lower = rel.lower().replace("\\", "/")
    parts = lower.split("/")
    if any(p in {"vendor", "third_party", "third-party", "vendors"} for p in parts):
        return True
    name = parts[-1] if parts else lower
    if name.endswith((".min.js", ".min.css", ".min.map", ".bundle.js")):
        return True
    # 超大打包产物常见名
    if name.endswith(".js") and any(x in name for x in (".umd.", ".esm.", ".chunk.")):
        return True
    return False


def is_security_hot_file(rel: str) -> bool:
    """鉴权/暴露面相关配置：优先审，空 findings 时强制复审。"""
    lower = rel.lower().replace("\\", "/")
    name = lower.rsplit("/", 1)[-1]
    if any(
        k in name
        for k in (
            "openapi",
            "swagger",
            "nginx",
            "dockerfile",
            "docker-compose",
            "compose.",
            "auth",
            "security",
            "cors",
            "middleware",
        )
    ):
        return True
    if lower.endswith((".yaml", ".yml")) and any(
        k in lower for k in ("deploy/", "api/", "gateway/", "ingress/", "k8s/", "helm/")
    ):
        return True
    return False


def _is_security_hot_file(rel: str) -> bool:
    return is_security_hot_file(rel)


def _allowed_file(path: Path) -> bool:
    suf = path.suffix.lower()
    if suf in DOC_OR_STYLE_SUFFIXES:
        return False
    return suf in ALLOWED_SUFFIXES


def _safe_rel(root: Path, path: Path) -> str | None:
    try:
        rel = path.relative_to(root.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if any(p == ".." for p in parts):
        return None
    rel_s = rel.as_posix()
    if is_sensitive_rel(rel_s):
        return None
    if _is_vendor_or_minified(rel_s):
        return None
    return rel_s


def list_review_files(
    root: Path,
    *,
    scope_root: Path | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """递归列出可审阅文件（相对 root 的路径）。"""
    scan = scope_root if scope_root is not None else root
    if not scan.is_dir():
        return []

    out: list[dict[str, Any]] = []

    def walk(base: Path) -> None:
        if len(out) >= limit:
            return
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for entry in entries:
            if len(out) >= limit:
                return
            name = entry.name
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if _is_skippable_dir(name):
                        continue
                    # 常见第三方目录整枝跳过
                    if name.lower() in {"vendor", "third_party", "third-party", "vendors"}:
                        continue
                    walk(entry)
                    continue
                if not entry.is_file() or not _allowed_file(entry):
                    continue
                rel = _safe_rel(root, entry)
                if not rel:
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                out.append({"path": rel, "bytes": size})
            except OSError:
                continue

    walk(scan)
    out.sort(key=lambda x: x["path"])
    return out


def _priority_key(rel: str) -> tuple[int, str]:
    """优先审：安全热文件 → 业务源码 → 普通配置。"""
    lower = rel.lower().replace("\\", "/")
    if _is_security_hot_file(lower):
        return (0, lower)
    score = 50
    for i, pref in enumerate(
        (
            "src/main/java/",
            "src/main/kotlin/",
            "frontend/src/",
            "backend/app/",
            "api/",
            "src/views/",
            "src/components/",
            "src/pages/",
            "app/routers/",
            "app/api/",
            "app/services/",
            "lib/",
            "tests/",
            "src/test/",
        )
    ):
        if lower.startswith(pref) or f"/{pref}" in f"/{lower}":
            score = 10 + i
            break
    # 普通配置/锁文件靠后（热文件已在上面提前）
    if any(lower.endswith(x) for x in (".json", ".yml", ".yaml", ".toml", ".xml", ".gradle")):
        score = max(score, 80)
    if lower.endswith(".sh"):
        score = min(score, 60)
    return (score, lower)


def select_files_for_review(
    root: Path,
    *,
    scope_root: Path | None,
    explicit_files: list[str] | None,
    cfg: CodeReviewConfig,
) -> tuple[list[str], list[str]]:
    """返回 (selected_rel_paths, warnings)。"""
    warnings: list[str] = []
    if explicit_files:
        selected: list[str] = []
        for raw in explicit_files:
            rel = (raw or "").strip().replace("\\", "/").lstrip("/")
            if not rel:
                continue
            if is_sensitive_rel(rel):
                warnings.append(f"跳过敏感路径：{rel}")
                continue
            target = (root / rel).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                warnings.append(f"路径不在工程内：{rel}")
                continue
            if not target.is_file():
                warnings.append(f"不是文件：{rel}")
                continue
            if not _allowed_file(target):
                warnings.append(f"后缀不在白名单：{rel}")
                continue
            if target.is_symlink():
                warnings.append(f"跳过符号链接：{rel}")
                continue
            selected.append(rel.replace("\\", "/"))
        if len(selected) > cfg.max_files:
            warnings.append(f"文件数超过上限 {cfg.max_files}，已截断")
            selected = selected[: cfg.max_files]
        return selected, warnings

    listed = list_review_files(root, scope_root=scope_root, limit=cfg.max_files * 4)
    rels = [x["path"] for x in listed]
    rels.sort(key=_priority_key)
    if len(rels) > cfg.max_files:
        warnings.append(f"扫描到 {len(rels)} 个文件，按优先级取前 {cfg.max_files} 个")
        rels = rels[: cfg.max_files]
    if not rels:
        warnings.append("未找到可审阅的源码文件（检查 scope 或后缀白名单）")
    return rels, warnings


def read_review_files(
    root: Path,
    rel_paths: list[str],
    cfg: CodeReviewConfig,
) -> tuple[list[dict[str, Any]], list[str], int]:
    """读取文件内容。返回 (files, warnings, total_bytes)。"""
    files: list[dict[str, Any]] = []
    warnings: list[str] = []
    total = 0

    for rel in rel_paths:
        rel = rel.replace("\\", "/")
        if is_sensitive_rel(rel):
            warnings.append(f"跳过敏感：{rel}")
            continue
        target = root / rel
        if target.is_symlink():
            warnings.append(f"跳过符号链接：{rel}")
            continue
        try:
            target = target.resolve()
            target.relative_to(root.resolve())
        except (ValueError, OSError):
            warnings.append(f"无法读取：{rel}")
            continue
        if not target.is_file():
            warnings.append(f"不是文件：{rel}")
            continue
        try:
            size = target.stat().st_size
        except OSError:
            warnings.append(f"无法 stat：{rel}")
            continue
        truncated = False
        read_size = size
        if read_size > cfg.max_file_bytes:
            read_size = cfg.max_file_bytes
            truncated = True
        if total + read_size > cfg.max_total_bytes:
            warnings.append(f"已达总读取上限 {cfg.max_total_bytes} 字节，停止加载更多文件")
            break
        try:
            raw = target.read_bytes()[:read_size]
            text = raw.decode("utf-8", errors="replace")
        except OSError:
            warnings.append(f"读取失败：{rel}")
            continue
        total += read_size
        files.append(
            {
                "path": rel,
                "bytes": size,
                "read_bytes": read_size,
                "truncated": truncated,
                "content": text,
            }
        )
    return files, warnings, total
