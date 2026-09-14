"""追加 JSONL 流水并做区间汇总。"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .parse import missing_tokens

_LOG = logging.getLogger(__name__)
_ENGINE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DIR = str(_ENGINE_ROOT / "data" / "usage")
_LEGACY_DIR = str(Path(__file__).resolve().parents[1] / "data" / "usage")
_TZ = ZoneInfo("Asia/Shanghai")
RETENTION_DAYS = 90
_migrated = False

LANE_LABELS = {
    "chat": "聊天 / 意图",
    "dsh_chat": "DSH 聊天",
    "pcb": "PCB 专家",
    "code_dev_discuss": "写码讨论",
    "dsh_cursor": "DSH Cursor 写码",
    "code_review": "审码",
    "code_commit": "提交门禁",
    "config_test": "配置探测",
    "unknown": "未标注车道",
}

_data_dir_override: str | None = None


def _migrate_legacy_ledger() -> None:
    """旧实现误写到 engine/app/data/usage，迁到 engine/data/usage。"""
    global _migrated
    if _migrated or _data_dir_override:
        return
    _migrated = True
    src = Path(_LEGACY_DIR) / "events.jsonl"
    dest_dir = Path(_DEFAULT_DIR)
    dest = dest_dir / "events.jsonl"
    if dest.is_file() or not src.is_file():
        return
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        src.replace(dest)
        lock = Path(_LEGACY_DIR) / "events.jsonl.lock"
        if lock.is_file():
            lock.unlink()
    except OSError:
        _LOG.warning("usage migrate legacy ledger failed", exc_info=True)


def _dir() -> str:
    if not _data_dir_override:
        _migrate_legacy_ledger()
    return _data_dir_override or _DEFAULT_DIR


def events_path() -> str:
    return os.path.join(_dir(), "events.jsonl")


def set_data_dir(path: str | None) -> None:
    global _data_dir_override
    _data_dir_override = path


def _now() -> datetime:
    return datetime.now(_TZ)


def _event_id(now: datetime) -> str:
    return f"usg_{now.strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}"


def _lock_path() -> str:
    return events_path() + ".lock"


def append_event(
    *,
    source: str,
    lane: str,
    provider: str,
    model: str,
    tokens: dict[str, Any] | None,
    ok: bool = True,
    job_id: str = "",
    error_class: str = "",
    ts: str | None = None,
) -> dict[str, Any] | None:
    """写一条流水。失败吞掉并打日志。ts 可回填历史 Job 时间。"""
    try:
        now = _parse_ts(ts) if ts else None
        if now is None:
            now = _now()
        body = missing_tokens() if not tokens else dict(tokens)
        evt = {
            "id": _event_id(now),
            "ts": now.isoformat(timespec="seconds"),
            "source": source if source in {"llm", "cursor"} else "llm",
            "lane": (lane or "unknown").strip() or "unknown",
            "provider": str(provider or "")[:80],
            "model": str(model or "")[:120],
            "prompt_tokens": int(body.get("prompt_tokens") or 0),
            "completion_tokens": int(body.get("completion_tokens") or 0),
            "cache_read_tokens": int(body.get("cache_read_tokens") or 0),
            "cache_write_tokens": int(body.get("cache_write_tokens") or 0),
            "reasoning_tokens": int(body.get("reasoning_tokens") or 0),
            "total_tokens": int(body.get("total_tokens") or 0),
            "quality": str(body.get("quality") or "missing"),
            "ok": bool(ok),
            "job_id": str(job_id or "")[:80],
            "error_class": str(error_class or "")[:80],
        }
        os.makedirs(_dir(), exist_ok=True)
        line = json.dumps(evt, ensure_ascii=False) + "\n"
        with open(_lock_path(), "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                with open(events_path(), "a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        return evt
    except Exception:
        _LOG.warning("usage append failed", exc_info=True)
        return None


def _parse_ts(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ)
    return dt.astimezone(_TZ)


def _iter_events() -> list[dict[str, Any]]:
    path = events_path()
    if not os.path.isfile(path):
        return []
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        return []
    return out


def known_job_ids(*, only_quality: str = "") -> set[str]:
    out: set[str] = set()
    for e in _iter_events():
        jid = str(e.get("job_id") or "").strip()
        if not jid:
            continue
        if only_quality and str(e.get("quality") or "") != only_quality:
            continue
        out.add(jid)
    return out


def drop_events_for_job(job_id: str) -> int:
    """删除指定 job_id 的流水（用于 missing → SDK 真值升级）。"""
    jid = str(job_id or "").strip()
    if not jid:
        return 0
    kept: list[str] = []
    removed = 0
    path = events_path()
    if not os.path.isfile(path):
        return 0
    for evt in _iter_events():
        if str(evt.get("job_id") or "").strip() == jid:
            removed += 1
            continue
        kept.append(json.dumps(evt, ensure_ascii=False))
    if removed:
        with open(_lock_path(), "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(kept) + ("\n" if kept else ""))
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    return removed


def _in_range(evt: dict[str, Any], start: datetime, end: datetime) -> bool:
    ts = _parse_ts(str(evt.get("ts") or ""))
    if ts is None:
        return False
    return start <= ts < end


def _empty_parts() -> dict[str, Any]:
    return {
        "calls": 0,
        "tokens": 0,
        "missing_calls": 0,
        "cache_hit": 0,
        "cache_miss": 0,
        "output": 0,
    }


def _event_parts(evt: dict[str, Any]) -> dict[str, int]:
    prompt = int(evt.get("prompt_tokens") or 0)
    hit = int(evt.get("cache_read_tokens") or 0)
    output = int(evt.get("completion_tokens") or 0) + int(evt.get("reasoning_tokens") or 0)
    total = int(evt.get("total_tokens") or 0)
    exclusive = prompt + output + hit
    # Cursor / DSH：inputTokens 不含 cacheRead；cache 常大于 input，不能按 OpenAI 从 prompt 里扣
    if hit > prompt:
        miss = prompt
        if total <= 0:
            total = exclusive
    elif hit and total and abs(exclusive - total) <= 2:
        miss = prompt
        if total <= 0:
            total = exclusive
    else:
        miss = max(0, prompt - hit) if prompt else 0
        if prompt == 0 and output == 0 and total:
            miss = total
        if total <= 0:
            total = prompt + output
    if total <= 0:
        total = miss + hit + output
    return {
        "tokens": total,
        "cache_hit": hit,
        "cache_miss": miss,
        "output": output,
    }


def _add_parts(slot: dict[str, Any], evt: dict[str, Any]) -> None:
    parts = _event_parts(evt)
    slot["calls"] += 1
    slot["tokens"] += parts["tokens"]
    slot["cache_hit"] += parts["cache_hit"]
    slot["cache_miss"] += parts["cache_miss"]
    slot["output"] += parts["output"]
    if str(evt.get("quality") or "") == "missing":
        slot["missing_calls"] += 1


def _empty_day() -> dict[str, Any]:
    return {
        "llm_calls": 0,
        "llm_tokens": 0,
        "llm_cache_hit": 0,
        "llm_cache_miss": 0,
        "llm_output": 0,
        "cursor_calls": 0,
        "cursor_tokens": 0,
        "cursor_cache_hit": 0,
        "cursor_cache_miss": 0,
        "cursor_output": 0,
        "calls": 0,
    }


def _hour_of(evt: dict[str, Any]) -> int:
    """北京时间小时 0–23。"""
    dt = _parse_ts(str(evt.get("ts") or ""))
    if dt is not None:
        return max(0, min(23, int(dt.hour)))
    raw = str(evt.get("ts") or "")
    if len(raw) >= 13 and raw[10] in "T ":
        try:
            return max(0, min(23, int(raw[11:13])))
        except ValueError:
            return 0
    return 0


def _add_day_parts(slot: dict[str, Any], evt: dict[str, Any], src: str) -> None:
    slot["calls"] += 1
    prefix = "cursor_" if src == "cursor" else "llm_"
    parts = _event_parts(evt)
    slot[prefix + "calls"] += 1
    slot[prefix + "tokens"] += parts["tokens"]
    slot[prefix + "cache_hit"] += parts["cache_hit"]
    slot[prefix + "cache_miss"] += parts["cache_miss"]
    slot[prefix + "output"] += parts["output"]


def _focus_day(on: str = "") -> datetime:
    """北京时间自然日 00:00；空或非法则今天；不可晚于今天。"""
    now = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    raw = str(on or "").strip()[:10]
    if not raw:
        return now
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=_TZ)
    except ValueError:
        return now
    if day > now:
        return now
    oldest = now - timedelta(days=RETENTION_DAYS - 1)
    if day < oldest:
        return oldest
    return day


def _month_span(focus: datetime) -> tuple[datetime, datetime]:
    """所选日所在自然月：1 号至月末；当月则截止今天（不含未来）。"""
    start = focus.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    now = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        nxt = start.replace(year=start.year + 1, month=1, day=1)
    else:
        nxt = start.replace(month=start.month + 1, day=1)
    end = nxt
    today_end = now + timedelta(days=1)
    if end > today_end:
        end = today_end
    if end <= start:
        end = start + timedelta(days=1)
    return start, end


def summarize(*, days: int = 7, source: str = "", on: str = "") -> dict[str, Any]:
    """按北京时间汇总；卡片与 hourly 锚定 on，monthly 为该日所在自然月。"""
    try:
        from .ingest_cursor import ingest_dsh_cursor_jobs

        ingest_dsh_cursor_jobs()
    except Exception:
        _LOG.warning("usage ingest dsh cursor failed", exc_info=True)
    try:
        from .ingest_dsh_llm import ingest_dsh_sessions

        ingest_dsh_sessions()
    except Exception:
        _LOG.warning("usage ingest dsh sessions failed", exc_info=True)
    days = max(1, min(int(days or 7), 90))
    focus = _focus_day(on)
    end = focus + timedelta(days=1)
    start = end - timedelta(days=days)
    events = [e for e in _iter_events() if _in_range(e, start, end)]
    if source in {"llm", "cursor"}:
        events = [e for e in events if e.get("source") == source]

    by_source = {"llm": _empty_parts(), "cursor": _empty_parts()}
    by_lane: dict[str, dict[str, Any]] = {}
    daily: dict[str, dict[str, Any]] = {}
    models: dict[str, dict[str, dict[str, Any]]] = {"llm": {}, "cursor": {}}
    today_key = focus.strftime("%Y-%m-%d")
    hourly: dict[int, dict[str, Any]] = {h: _empty_day() for h in range(24)}

    for evt in events:
        src = evt.get("source") if evt.get("source") in by_source else "llm"
        lane = str(evt.get("lane") or "unknown")
        model = str(evt.get("model") or "").strip() or "unknown"
        _add_parts(by_source[src], evt)
        slot = by_lane.setdefault(
            f"{src}:{lane}",
            {
                "lane": lane,
                "label": LANE_LABELS.get(lane, lane),
                "calls": 0,
                "tokens": 0,
                "source": src,
            },
        )
        slot["calls"] += 1
        slot["tokens"] += int(evt.get("total_tokens") or 0)
        mslot = models[src].setdefault(
            model,
            {**_empty_parts(), "model": model, "provider": str(evt.get("provider") or "")},
        )
        _add_parts(mslot, evt)
        day = str(evt.get("ts") or "")[:10]
        dslot = daily.setdefault(day, _empty_day())
        _add_day_parts(dslot, evt, src)
        if day == today_key:
            _add_day_parts(hourly[_hour_of(evt)], evt, src)

    day_rows = []
    cur = start
    while cur < end:
        key = cur.strftime("%Y-%m-%d")
        row = daily.get(key) or _empty_day()
        day_rows.append({"date": key, **row})
        cur += timedelta(days=1)

    hour_rows = [{"hour": h, **hourly[h]} for h in range(24)]
    m_start, m_end = _month_span(focus)
    monthly_map: dict[str, dict[str, Any]] = {}
    for evt in _iter_events():
        if source in {"llm", "cursor"} and evt.get("source") != source:
            continue
        if not _in_range(evt, m_start, m_end):
            continue
        src = evt.get("source") if evt.get("source") in {"llm", "cursor"} else "llm"
        day = str(evt.get("ts") or "")[:10]
        _add_day_parts(monthly_map.setdefault(day, _empty_day()), evt, src)
    month_rows: list[dict[str, Any]] = []
    cur_m = m_start
    while cur_m < m_end:
        key = cur_m.strftime("%Y-%m-%d")
        month_rows.append({"date": key, **(monthly_map.get(key) or _empty_day())})
        cur_m += timedelta(days=1)

    today_row = daily.get(today_key) or monthly_map.get(today_key) or _empty_day()
    today = {
        "llm_tokens": today_row["llm_tokens"],
        "cursor_tokens": today_row["cursor_tokens"],
        "calls": today_row["calls"],
        "llm_calls": today_row["llm_calls"],
        "cursor_calls": today_row["cursor_calls"],
        "llm": {
            "calls": today_row["llm_calls"],
            "tokens": today_row["llm_tokens"],
            "cache_hit": today_row["llm_cache_hit"],
            "cache_miss": today_row["llm_cache_miss"],
            "output": today_row["llm_output"],
        },
        "cursor": {
            "calls": today_row["cursor_calls"],
            "tokens": today_row["cursor_tokens"],
            "cache_hit": today_row["cursor_cache_hit"],
            "cache_miss": today_row["cursor_cache_miss"],
            "output": today_row["cursor_output"],
        },
    }

    def _model_list(src: str) -> list[dict[str, Any]]:
        return sorted(
            models[src].values(),
            key=lambda x: (-int(x["tokens"]), str(x.get("model") or "")),
        )

    llm = dict(by_source["llm"])
    llm["models"] = _model_list("llm")
    cursor = dict(by_source["cursor"])
    cursor["models"] = _model_list("cursor")
    return {
        "ok": True,
        "days": days,
        "from": start.strftime("%Y-%m-%d"),
        "to": (end - timedelta(seconds=1)).strftime("%Y-%m-%d"),
        "tz": "Asia/Shanghai",
        "on": today_key,
        "month": m_start.strftime("%Y-%m"),
        "month_from": m_start.strftime("%Y-%m-%d"),
        "month_to": (m_end - timedelta(seconds=1)).strftime("%Y-%m-%d"),
        "today": today,
        "llm": llm,
        "cursor": cursor,
        "by_lane": sorted(by_lane.values(), key=lambda x: (-int(x["tokens"]), x["lane"])),
        "daily": day_rows,
        "monthly": month_rows,
        "hourly": hour_rows,
    }


def list_events(
    *,
    limit: int = 10,
    offset: int = 0,
    source: str = "",
    page: int | None = None,
    page_size: int | None = None,
    on: str = "",
) -> dict[str, Any]:
    rows = _iter_events()
    if source in {"llm", "cursor"}:
        rows = [e for e in rows if e.get("source") == source]
    day = str(on or "").strip()[:10]
    if len(day) == 10 and day[4] == "-" and day[7] == "-":
        rows = [e for e in rows if str(e.get("ts") or "")[:10] == day]
    rows.sort(key=lambda e: str(e.get("ts") or ""), reverse=True)
    total = len(rows)
    ps = int(page_size or 0) or int(limit or 10)
    ps = max(1, min(ps, 200))
    if page is not None:
        pg = max(1, int(page or 1))
        off = (pg - 1) * ps
    else:
        off = max(0, int(offset or 0))
        pg = (off // ps) + 1 if ps else 1
    sliced = rows[off : off + ps]
    events: list[dict[str, Any]] = []
    for e in sliced:
        row = dict(e)
        lane = str(row.get("lane") or "")
        row["label"] = LANE_LABELS.get(lane, lane)
        q = str(row.get("quality") or "")
        if q == "sdk" and row.get("source") == "llm":
            row["quality"] = "session"
        events.append(row)
    return {
        "ok": True,
        "events": events,
        "count": len(events),
        "total": total,
        "page": pg,
        "page_size": ps,
    }


def prune_old(*, keep_days: int = RETENTION_DAYS) -> int:
    """删除过期流水。返回删除条数。"""
    keep_days = max(7, int(keep_days or RETENTION_DAYS))
    cutoff = _now() - timedelta(days=keep_days)
    kept: list[str] = []
    removed = 0
    path = events_path()
    if not os.path.isfile(path):
        return 0
    for evt in _iter_events():
        ts = _parse_ts(str(evt.get("ts") or ""))
        if ts is None or ts >= cutoff:
            kept.append(json.dumps(evt, ensure_ascii=False))
        else:
            removed += 1
    if removed:
        os.makedirs(_dir(), exist_ok=True)
        with open(_lock_path(), "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(kept) + ("\n" if kept else ""))
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    return removed
