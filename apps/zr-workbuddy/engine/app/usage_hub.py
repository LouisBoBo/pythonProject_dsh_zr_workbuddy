"""企业用量汇总（P0：与引擎同进程、只绑回环；生产可拆独立服务）。"""
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

_LOG = logging.getLogger(__name__)
_ENGINE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DIR = str(_ENGINE_ROOT / "data" / "usage_hub")
_TZ = ZoneInfo("Asia/Shanghai")

_data_dir_override: str | None = None


def set_data_dir(path: str | None) -> None:
    global _data_dir_override
    _data_dir_override = path


def _dir() -> str:
    return _data_dir_override or _DEFAULT_DIR


def events_path() -> str:
    return os.path.join(_dir(), "events.jsonl")


def _lock_path() -> str:
    return events_path() + ".lock"


def _now() -> datetime:
    return datetime.now(_TZ)


def _parse_ts(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ)
    return dt.astimezone(_TZ)


def _iter_hub_events() -> list[dict[str, Any]]:
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
                if isinstance(row, dict) and row.get("id"):
                    out.append(row)
    except OSError:
        _LOG.warning("usage_hub read failed", exc_info=True)
    return out


def _iter_events() -> list[dict[str, Any]]:
    """汇总视图：本机账本 + hub 上报库按 id 去重（上报开启后不会双计）。"""
    by_id: dict[str, dict[str, Any]] = {}
    try:
        from .usage.store import iter_all_events

        for evt in iter_all_events():
            eid = str(evt.get("id") or "").strip()
            if eid:
                by_id[eid] = evt
    except Exception:
        _LOG.debug("usage_hub merge local ledger skipped", exc_info=True)
    for evt in _iter_hub_events():
        eid = str(evt.get("id") or "").strip()
        if eid:
            by_id[eid] = evt
    return list(by_id.values())


def _known_ids() -> set[str]:
    return {str(e.get("id") or "") for e in _iter_hub_events() if e.get("id")}


def _user_labels(uid: str) -> dict[str, str]:
    try:
        from .auth.users import find_user_by_id

        u = find_user_by_id(uid)
        if u:
            uname = str(u.get("username") or "").strip()
            dname = str(u.get("display_name") or uname or uid).strip()
            return {"username": uname, "display_name": dname}
    except Exception:
        pass
    return {"username": "", "display_name": uid}


def _report_token() -> str:
    try:
        from .config_store import load_config

        cfg = load_config().get("usage") or {}
        if isinstance(cfg, dict):
            return str(cfg.get("report_token") or "").strip()
    except Exception:
        pass
    return ""


def check_ingest_token(authorization: str | None) -> bool:
    """校验机器票据。未配置 report_token 时拒绝入库（防空票据伪造流水）。"""
    expect = _report_token()
    raw = (authorization or "").strip()
    got = ""
    if raw.lower().startswith("bearer "):
        got = raw[7:].strip()
    elif raw:
        got = raw
    if not expect:
        return False
    if not got or len(got) != len(expect):
        return False
    return secrets.compare_digest(got, expect)


def ingest_batch(body: dict[str, Any]) -> dict[str, Any]:
    """按 id 幂等写入；返回 accepted / duplicate / rejected。

    防护：user_id 须为本机用户库已知账号；单事件 total_tokens 上限；部件和不得远超 total。
    """
    events = body.get("events") if isinstance(body, dict) else None
    if not isinstance(events, list):
        return {"ok": False, "detail": "events 须为数组", "accepted": [], "duplicate": [], "rejected": []}
    mid = str(body.get("machine_id") or "")[:80]
    batch_uid = str(body.get("user_id") or "").strip()[:80]
    known = _known_ids()
    known_users: set[str] = set()
    try:
        from .auth.users import list_public_users

        for u in list_public_users(include_disabled=True):
            uid0 = str(u.get("id") or "").strip()
            if uid0:
                known_users.add(uid0)
    except Exception:
        _LOG.debug("ingest known users skipped", exc_info=True)
    accepted: list[str] = []
    duplicate: list[str] = []
    rejected: list[dict[str, str]] = []
    lines: list[str] = []
    max_tokens = 5_000_000  # 单事件上限，防灌爆汇总

    def _reject(eid: str, reason: str) -> None:
        rejected.append({"id": eid[:80], "reason": reason})

    for raw in events[:200]:
        if not isinstance(raw, dict):
            continue
        eid = str(raw.get("id") or "").strip()
        if not eid or not eid.startswith("usg_"):
            continue
        if eid in known:
            duplicate.append(eid)
            continue
        uid = str(raw.get("user_id") or batch_uid or "").strip()[:80]
        if not uid:
            _reject(eid, "missing_user_id")
            continue
        if known_users and uid not in known_users:
            _reject(eid, "unknown_user_id")
            continue
        try:
            total = int(raw.get("total_tokens") or 0)
            prompt = int(raw.get("prompt_tokens") or 0)
            completion = int(raw.get("completion_tokens") or 0)
            cache_r = int(raw.get("cache_read_tokens") or 0)
            cache_w = int(raw.get("cache_write_tokens") or 0)
            reasoning = int(raw.get("reasoning_tokens") or 0)
        except (TypeError, ValueError):
            _reject(eid, "bad_token_fields")
            continue
        if total < 0 or prompt < 0 or completion < 0 or cache_r < 0 or cache_w < 0 or reasoning < 0:
            _reject(eid, "negative_tokens")
            continue
        if total > max_tokens:
            _reject(eid, "tokens_too_large")
            continue
        parts = prompt + completion + cache_r + cache_w + reasoning
        if parts > 0 and total > 0 and parts > total * 5 + 1000:
            _reject(eid, "parts_implausible")
            continue
        src = raw.get("source") if raw.get("source") in {"llm", "cursor"} else "llm"
        row = {
            "id": eid[:80],
            "ts": str(raw.get("ts") or _now().isoformat(timespec="seconds"))[:40],
            "source": src,
            "lane": str(raw.get("lane") or "unknown")[:80],
            "provider": str(raw.get("provider") or "")[:80],
            "model": str(raw.get("model") or "")[:120],
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cache_read_tokens": cache_r,
            "cache_write_tokens": cache_w,
            "reasoning_tokens": reasoning,
            "total_tokens": total,
            "quality": str(raw.get("quality") or "")[:40],
            "ok": bool(raw.get("ok", True)),
            "user_id": uid,
            "machine_id": str(raw.get("machine_id") or mid or "")[:80],
        }
        lines.append(json.dumps(row, ensure_ascii=False))
        known.add(eid)
        accepted.append(eid)
    if lines:
        os.makedirs(_dir(), exist_ok=True)
        with open(_lock_path(), "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                with open(events_path(), "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    return {"ok": True, "accepted": accepted, "duplicate": duplicate, "rejected": rejected}


def _empty_src() -> dict[str, int]:
    return {"calls": 0, "tokens": 0, "missing_calls": 0}


def _add(slot: dict[str, int], evt: dict[str, Any]) -> None:
    slot["calls"] += 1
    slot["tokens"] += int(evt.get("total_tokens") or 0)
    if str(evt.get("quality") or "") == "missing":
        slot["missing_calls"] += 1


def _parse_range(from_s: str, to_s: str) -> tuple[datetime, datetime]:
    now = _now()
    end_d = _parse_ts((to_s or "").strip()[:10] + "T00:00:00") if (to_s or "").strip() else None
    start_d = _parse_ts((from_s or "").strip()[:10] + "T00:00:00") if (from_s or "").strip() else None
    if end_d is None:
        end_d = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if start_d is None:
        start_d = end_d.replace(day=1)
    end = end_d + timedelta(days=1)
    return start_d, end


def company_summary(*, from_date: str = "", to_date: str = "") -> dict[str, Any]:
    start, end = _parse_range(from_date, to_date)
    llm = _empty_src()
    cursor = _empty_src()
    users: set[str] = set()
    for evt in _iter_events():
        ts = _parse_ts(str(evt.get("ts") or ""))
        if ts is None or ts < start or ts >= end:
            continue
        uid = str(evt.get("user_id") or "").strip()
        if uid:
            users.add(uid)
        src = evt.get("source") if evt.get("source") in {"llm", "cursor"} else "llm"
        _add(llm if src == "llm" else cursor, evt)
    return {
        "ok": True,
        "tz": "Asia/Shanghai",
        "from": start.strftime("%Y-%m-%d"),
        "to": (end - timedelta(seconds=1)).strftime("%Y-%m-%d"),
        "people": len(users),
        "llm": llm,
        "cursor": cursor,
        "note": "公司 Key 总额只看 llm；Cursor 另列，不能加总成一笔钱。可对照 DeepSeek 控制台。",
    }


def people_summary(*, from_date: str = "", to_date: str = "", grain: str = "month") -> dict[str, Any]:
    start, end = _parse_range(from_date, to_date)
    grain = grain if grain in {"day", "month"} else "month"
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    periods: set[str] = set()
    for evt in _iter_events():
        ts = _parse_ts(str(evt.get("ts") or ""))
        if ts is None or ts < start or ts >= end:
            continue
        uid = str(evt.get("user_id") or "").strip()
        if not uid:
            continue
        period = ts.strftime("%Y-%m-%d") if grain == "day" else ts.strftime("%Y-%m")
        periods.add(period)
        key = (uid, period)
        if key not in buckets:
            buckets[key] = {
                "user_id": uid,
                "period": period,
                "llm": _empty_src(),
                "cursor": _empty_src(),
            }
        src = evt.get("source") if evt.get("source") in {"llm", "cursor"} else "llm"
        _add(buckets[key]["llm" if src == "llm" else "cursor"], evt)

    # 无流水时仍给出筛选锚定 period，便于补齐全体员工（含 admin）零行
    if not periods:
        if grain == "day":
            periods.add(start.strftime("%Y-%m-%d"))
        else:
            periods.add(start.strftime("%Y-%m"))

    # 本机用户库全体员工（含 admin）补零，避免「有用量才出现」
    try:
        from .auth.users import list_public_users

        for u in list_public_users():
            uid = str(u.get("id") or "").strip()
            if not uid:
                continue
            for period in periods:
                key = (uid, period)
                if key not in buckets:
                    buckets[key] = {
                        "user_id": uid,
                        "period": period,
                        "llm": _empty_src(),
                        "cursor": _empty_src(),
                    }
    except Exception:
        _LOG.debug("people_summary pad users skipped", exc_info=True)

    rows = sorted(buckets.values(), key=lambda r: (r["period"], r["user_id"]))
    out_rows: list[dict[str, Any]] = []
    for r in rows:
        labels = _user_labels(str(r["user_id"]))
        out_rows.append(
            {
                "user_id": r["user_id"],
                "username": labels["username"],
                "display_name": labels["display_name"],
                "period": r["period"],
                "llm_tokens": r["llm"]["tokens"],
                "llm_calls": r["llm"]["calls"],
                "llm_missing_calls": r["llm"]["missing_calls"],
                "cursor_tokens": r["cursor"]["tokens"],
                "cursor_calls": r["cursor"]["calls"],
                "cursor_missing_calls": r["cursor"]["missing_calls"],
            }
        )
    return {
        "ok": True,
        "tz": "Asia/Shanghai",
        "grain": grain,
        "from": start.strftime("%Y-%m-%d"),
        "to": (end - timedelta(seconds=1)).strftime("%Y-%m-%d"),
        "rows": out_rows,
    }
