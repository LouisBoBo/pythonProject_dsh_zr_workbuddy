"""只读采集 DSH llm-meter 插件落盘（~/.dsh/llm-meter/events.jsonl）。

插件挂 llm/stream，覆盖聊天 / knowledge / memory 等旁路。
文件存在且非空时，summarize 侧会跳过 session/memory/title 补采，避免双计。
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .store import (
    _current_user_id,
    _parse_ts,
    append_event,
    known_job_ids,
)

_LOG = logging.getLogger(__name__)
_last_ingest = 0.0
_file_stamp: dict[str, tuple[float, int]] = {}
_earliest_meter_dt: datetime | None = None

# 单文件防护：过大 / 过多行则截断，避免 summarize 路径 OOM
_MAX_FILE_BYTES = 32 * 1024 * 1024
_MAX_LINES = 200_000
_MAX_LINE_CHARS = 32_768

_ALLOWED_SOURCES = frozenset(
    {
        "dsh_chat",
        "dsh_knowledge",
        "dsh_memory",
        "dsh_title",
        "dsh_other",
        "dsh_llm_meter",
    }
)

_SKIP_SUFFIXES = (".lock", ".tmp", ".bak", ".swp", ".partial")


def _safe_home_path(raw: str, fallback: Path) -> Path:
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        cand = Path(text).expanduser().resolve()
        home = Path.home().resolve()
    except OSError:
        return fallback
    if cand == home or home not in cand.parents:
        _LOG.warning("ignore LLM_METER_DIR outside home")
        return fallback
    return cand


def _meter_dir() -> Path:
    fallback = Path.home() / ".dsh" / "llm-meter"
    env = (os.environ.get("DSH_LLM_METER_DIR") or "").strip()
    return _safe_home_path(env, fallback) if env else fallback


def meter_events_path() -> Path:
    return _meter_dir() / "events.jsonl"


def meter_active() -> bool:
    """插件已落盘（有内容）→ 宿主旁路以 meter 为准。"""
    from . import store as st

    if getattr(st, "_data_dir_override", None):
        return False
    path = meter_events_path()
    try:
        if path.is_symlink():
            return False
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def first_meter_datetime() -> datetime | None:
    """插件账本里最早一条 meter 的北京时间。测试覆盖 data_dir 时只看引擎账本。"""
    global _earliest_meter_dt
    from . import store as st

    if getattr(st, "_data_dir_override", None):
        return st._first_meter_ts_from_ledger()
    if _earliest_meter_dt is not None:
        return _earliest_meter_dt
    earliest: datetime | None = None
    for path in _iter_meter_files(_meter_dir()):
        dt = _earliest_ts_in_file(path)
        if dt is None:
            continue
        if earliest is None or dt < earliest:
            earliest = dt
    if earliest is None:
        earliest = st._first_meter_ts_from_ledger()
    if earliest is not None:
        _earliest_meter_dt = earliest
    return earliest


def _earliest_ts_in_file(path: Path) -> datetime | None:
    earliest: datetime | None = None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size <= 0 or size > _MAX_FILE_BYTES:
        return None
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= _MAX_LINES:
                    break
                if len(line) > _MAX_LINE_CHARS:
                    continue
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                dt = _parse_ts(str(row.get("ts") or ""))
                if dt is None:
                    continue
                if earliest is None or dt < earliest:
                    earliest = dt
    except OSError:
        return earliest
    return earliest


def _is_meter_data_name(name: str) -> bool:
    """只认 events.jsonl 与轮转 events.jsonl.N / .YYYYMMDD；排除 .lock/.tmp。"""
    if name == "events.jsonl":
        return True
    if not name.startswith("events.jsonl."):
        return False
    lower = name.lower()
    if any(lower.endswith(suf) for suf in _SKIP_SUFFIXES):
        return False
    # events.jsonl.lock / events.jsonl.tmp 也被 startswith 命中，上面已挡
    return True


def _path_under_root(path: Path, root: Path) -> Path | None:
    """解析后必须仍在 root 下；拒绝 symlink 逃逸。"""
    try:
        if path.is_symlink():
            return None
        root_r = root.resolve()
        cand = path.resolve()
        cand.relative_to(root_r)
        if not cand.is_file():
            return None
        return cand
    except (OSError, ValueError):
        return None


def _iter_meter_files(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    primary = root / "events.jsonl"
    ordered: list[Path] = []
    if primary.exists():
        ordered.append(primary)
    rotated = sorted(
        (p for p in entries if p.is_file() and _is_meter_data_name(p.name) and p.name != "events.jsonl"),
        key=lambda p: p.name,
    )
    ordered.extend(rotated)
    for path in ordered:
        safe = _path_under_root(path, root)
        if safe is not None:
            yield safe


def _int(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


def _tokens_from_row(row: dict[str, Any]) -> dict[str, Any]:
    prompt = _int(row.get("prompt_tokens"))
    completion = _int(row.get("completion_tokens"))
    cache_read = _int(row.get("cache_read_tokens"))
    cache_write = _int(row.get("cache_write_tokens"))
    reasoning = _int(row.get("reasoning_tokens"))
    total = _int(row.get("total_tokens"))
    # LOCKED 2026-09-17：官网口径合计 = prompt + completion + cache；reasoning 只作明细；未经允许不得改
    base = prompt + completion + cache_read + cache_write
    if total <= 0:
        total = base
    elif reasoning > 0 and total == base + reasoning:
        # 插件误把 reasoning 再加一遍时纠正
        total = base
    quality = str(row.get("quality") or "").strip() or (
        "provider" if total > 0 else "missing"
    )
    if quality not in {"provider", "sdk", "session", "estimate", "missing"}:
        quality = "provider" if total > 0 else "missing"
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "reasoning_tokens": reasoning,
        "total_tokens": total,
        "quality": quality,
    }


def _lane_from_row(row: dict[str, Any]) -> str:
    raw = str(row.get("source") or row.get("lane") or "dsh_other").strip()
    if raw in _ALLOWED_SOURCES:
        return raw
    if raw.startswith("dsh_"):
        return raw[:40]
    return "dsh_other"


def _ingest_file(path: Path, *, known: set[str]) -> int:
    added = 0
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    if size <= 0:
        return 0
    if size > _MAX_FILE_BYTES:
        _LOG.warning("skip oversized llm-meter file path=%s size=%s", path, size)
        return 0
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= _MAX_LINES:
                    _LOG.warning("llm-meter truncate path=%s at %s lines", path, _MAX_LINES)
                    break
                if len(line) > _MAX_LINE_CHARS:
                    continue
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                job_id = str(row.get("id") or "").strip()
                if not job_id or job_id in known:
                    continue
                raw_id = job_id
                if not job_id.startswith("meter_"):
                    job_id = ("meter_" + job_id)[:80]
                tokens = _tokens_from_row(row)
                provider = str(row.get("provider") or "deepseek")
                if "deepseek" in provider.lower():
                    provider = "deepseek"
                model = str(row.get("model") or "deepseek-v4-flash")
                ok = row.get("ok")
                if ok is None:
                    ok = not str(row.get("error") or "").strip()
                ts = str(row.get("ts") or "").strip() or None
                # 不信任 meter 文件里的 user_id；不回落 active.json（多账号会串账）
                # 有请求 ContextVar（用量 API set_current_user）则归当前登录账号；否则空串，等启动归户
                row_uid = _current_user_id(allow_active_fallback=False)[:80]
                evt = append_event(
                    source="llm",
                    lane=_lane_from_row(row),
                    provider=provider[:80],
                    model=model[:120],
                    tokens=tokens,
                    ok=bool(ok),
                    job_id=job_id[:80],
                    error_class=str(row.get("error") or row.get("finish") or "")[:80],
                    ts=ts,
                    user_id=row_uid,
                    allow_active_fallback=False,
                )
                if evt is not None:
                    added += 1
                    known.add(job_id[:80])
                    known.add(raw_id)
    except OSError:
        return 0
    return added


def ingest_llm_meter(*, force: bool = False) -> int:
    """扫描 ~/.dsh/llm-meter，把插件流水记入引擎账本。"""
    global _last_ingest
    now = time.monotonic()
    if not force and now - _last_ingest < 2.0:
        return 0
    from . import store as st

    if not force and getattr(st, "_data_dir_override", None):
        return 0
    _last_ingest = now
    root = _meter_dir()
    if not root.is_dir():
        return 0
    known = known_job_ids()
    added = 0
    for path in _iter_meter_files(root):
        try:
            key = str(path)
            st_mtime = path.stat().st_mtime
            size = path.stat().st_size
        except OSError:
            continue
        stamp = (st_mtime, size)
        if not force and _file_stamp.get(key) == stamp:
            continue
        try:
            n = _ingest_file(path, known=known)
        except Exception:
            _LOG.warning("ingest llm-meter failed path=%s", path, exc_info=True)
            continue
        added += n
        _file_stamp[key] = stamp
    if added:
        _LOG.info("ingested %s llm-meter events into usage ledger", added)
    return added
