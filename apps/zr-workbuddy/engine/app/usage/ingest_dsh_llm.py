"""只读采集 DSH 宿主会话里的 LLM usage，不改宿主/插件源码。"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .parse import from_sdk_usage
from .store import append_event, as_shanghai, exclude_at_or_after_cutoff, known_job_ids

_LOG = logging.getLogger(__name__)
_last_ingest = 0.0
_file_stamp: dict[str, float] = {}


def _safe_home_path(raw: str, fallback: Path) -> Path:
    """环境变量覆盖必须落在当前用户 HOME 之下，且不能就是 HOME 本身。"""
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        cand = Path(text).expanduser().resolve()
        home = Path.home().resolve()
    except OSError:
        return fallback
    if cand == home or home not in cand.parents:
        _LOG.warning("ignore DSH_SESSIONS_DIR outside home")
        return fallback
    return cand


def _sessions_root() -> Path:
    fallback = Path.home() / ".dsh" / "sessions"
    env = (os.environ.get("DSH_SESSIONS_DIR") or "").strip()
    return _safe_home_path(env, fallback) if env else fallback


def _iter_session_files(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    try:
        root_r = root.resolve()
    except OSError:
        return
    for path in root.rglob("session.jsonl*"):
        name = path.name
        if name not in {"session.jsonl", "session.jsonl.zstd"}:
            continue
        try:
            if path.is_symlink():
                continue
            cand = path.resolve()
            cand.relative_to(root_r)
            if not cand.is_file():
                continue
        except (OSError, ValueError):
            continue
        yield cand


def _iter_lines(path: Path) -> Iterator[str]:
    if path.name.endswith(".zstd"):
        try:
            proc = subprocess.Popen(
                ["zstd", "-d", "-c", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except FileNotFoundError:
            _LOG.warning("zstd not found; skip DSH session %s", path)
            return
        try:
            if proc.stdout is None:
                return
            yield from proc.stdout
        finally:
            try:
                if proc.stdout is not None:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=8)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        return
    with path.open(encoding="utf-8") as f:
        yield from f


def _session_id_from_path(path: Path) -> str:
    parent = path.parent.name
    if parent.startswith("session-"):
        return parent
    return ""


def _ts_from_ms(ms: Any) -> str:
    try:
        n = int(ms)
    except (TypeError, ValueError):
        return ""
    if n > 10_000_000_000:
        n = n / 1000.0
    try:
        from .store import _TZ

        return datetime.fromtimestamp(n, tz=timezone.utc).astimezone(_TZ).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def _provider_name(raw: str) -> str:
    p = (raw or "").strip().lower()
    if p in {"deepseek-official", "deepseek", "deepseek-api"}:
        return "deepseek"
    if p.startswith("ollama"):
        return "ollama"
    return (raw or "deepseek")[:80]


def _ingest_file(path: Path, *, known: set[str], before: datetime | None = None) -> int:
    sid = _session_id_from_path(path)
    model = ""
    provider = "deepseek"
    added = 0
    for line in _iter_lines(path):
        compact = line.replace(" ", "")
        if (
            '"type":"usage"' not in compact
            and '"type":"request/header"' not in compact
            and '"type":"session"' not in compact
        ):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        typ = str(obj.get("type") or "")
        if typ == "session":
            sid = str(obj.get("id") or sid).strip() or sid
            continue
        data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
        if typ == "request/header":
            header = data.get("header") if isinstance(data.get("header"), dict) else {}
            cfg = header.get("config") if isinstance(header.get("config"), dict) else {}
            model = str(cfg.get("model") or model).strip() or model
            provider = _provider_name(str(cfg.get("provider") or provider))
            continue
        if typ != "assistant/chunk":
            continue
        chunk = data.get("chunk") if isinstance(data.get("chunk"), dict) else {}
        if str(chunk.get("type") or "") != "usage":
            continue
        usage = chunk.get("usage")
        tokens = from_sdk_usage(usage)
        if not tokens:
            continue
        tokens["quality"] = "session"
        turn = data.get("turn")
        step = data.get("step")
        job_id = f"{sid}:t{turn}:s{step}" if sid else ""
        if not job_id or job_id in known:
            continue
        ts = _ts_from_ms(obj.get("time"))
        if exclude_at_or_after_cutoff(ts, before):
            continue
        evt = append_event(
            source="llm",
            lane="dsh_chat",
            provider=provider,
            model=model or "deepseek-v4-flash",
            tokens=tokens,
            ok=True,
            job_id=job_id,
            ts=ts,
        )
        if evt is not None:
            added += 1
            known.add(job_id)
    return added


def ingest_dsh_sessions(*, force: bool = False, before: datetime | str | None = None) -> int:
    """扫描 ~/.dsh/sessions，把宿主聊天 LLM usage 记入引擎账本。

    before：只采该时刻之前的步进（meter 启用后用来避免与 meter_* 双计）。
    """
    global _last_ingest
    now = time.monotonic()
    if not force and now - _last_ingest < 2.0:
        return 0
    from . import store as st

    if not force and getattr(st, "_data_dir_override", None):
        return 0
    _last_ingest = now
    known = known_job_ids()
    added = 0
    cutoff = as_shanghai(before)
    root = _sessions_root()
    for path in _iter_session_files(root):
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if not force and _file_stamp.get(key) == mtime:
            continue
        try:
            n = _ingest_file(path, known=known, before=cutoff)
        except Exception:
            _LOG.warning("ingest dsh session failed path=%s", path, exc_info=True)
            continue
        added += n
        _file_stamp[key] = mtime
    if added:
        _LOG.info("ingested %s DSH chat LLM usage events", added)
    return added
