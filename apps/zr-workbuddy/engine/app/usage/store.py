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
    "dsh_knowledge": "DSH 知识库抽取",
    "dsh_memory": "DSH 记忆整理",
    "dsh_title": "DSH 会话标题",
    "dsh_other": "DSH 其它 LLM",
    "dsh_llm_meter": "DSH llm-meter",
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


def _current_user_id(*, allow_active_fallback: bool = True) -> str:
    """优先请求内 ContextVar（Bearer）；后台任务才可回落 active.json。"""
    try:
        from ..auth import current_user_id, get_active_user

        uid = (current_user_id() or "").strip()
        if uid:
            return uid
        if not allow_active_fallback:
            return ""
        active = get_active_user()
        if active and active.get("id"):
            return str(active["id"]).strip()
    except Exception:
        _LOG.debug("usage resolve user_id skipped", exc_info=True)
    return ""


def _match_user(evt: dict[str, Any], user_id: str) -> bool:
    """个人用量只认明确归属；禁止空 user_id 旁路对全员可见（多账号串账）。"""
    return str(evt.get("user_id") or "").strip() == str(user_id or "").strip()


def _resolve_orphan_bind_uid(preferred: str = "") -> str:
    """解析历史无主流水的归户目标：优先入参 → hebo → 首位 admin → 首位用户。"""
    uid = (preferred or "").strip()
    if uid:
        return uid
    try:
        from ..auth.users import find_user, list_public_users

        hebo = find_user("hebo")
        if hebo and str(hebo.get("id") or "").strip():
            return str(hebo["id"]).strip()
        users = list_public_users()
        for u in users:
            if str(u.get("role") or "") == "admin" and str(u.get("id") or "").strip():
                return str(u["id"]).strip()
        if users and str(users[0].get("id") or "").strip():
            return str(users[0]["id"]).strip()
    except Exception:
        _LOG.debug("usage resolve orphan bind uid skipped", exc_info=True)
    return ""


def backfill_orphan_user_id(*, default_user_id: str = "") -> int:
    """一次性：把无 user_id 的历史流水（含 meter/dsh 旁路）归到本机账号。

    v4：去掉「空旁路全员可见」后，必须落户，否则个人页会漏计。
    """
    uid = _resolve_orphan_bind_uid(default_user_id)
    if not uid:
        return 0
    marker = os.path.join(_dir(), ".orphan_bound_v4")
    if os.path.isfile(marker):
        return 0
    path = events_path()
    if not os.path.isfile(path):
        try:
            os.makedirs(_dir(), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                f.write(f"bound={uid}\nchanged=0\n")
        except OSError:
            pass
        return 0
    changed = 0
    rewritten: list[str] = []
    try:
        with open(_lock_path(), "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                for evt in _iter_events():
                    if not str(evt.get("user_id") or "").strip():
                        evt = dict(evt)
                        evt["user_id"] = uid
                        changed += 1
                    rewritten.append(json.dumps(evt, ensure_ascii=False))
                if changed:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("\n".join(rewritten) + ("\n" if rewritten else ""))
                        f.flush()
                        os.fsync(f.fileno())
                with open(marker, "w", encoding="utf-8") as f:
                    f.write(f"bound={uid}\nchanged={changed}\n")
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception:
        _LOG.warning("usage backfill orphan user_id failed", exc_info=True)
        return 0
    if changed:
        _LOG.info("usage: 已将 %d 条无账号流水归到 %s", changed, uid)
    return changed


_METER_SUPERSEDE_LANES = frozenset({"dsh_chat", "dsh_memory", "dsh_title", "dsh_other"})
_METER_SUPERSEDE_QUALITY = frozenset({"session", "estimate", "missing"})


def _first_meter_ts_from_ledger() -> datetime | None:
    earliest: datetime | None = None
    for e in _iter_events():
        if not str(e.get("job_id") or "").startswith("meter_"):
            continue
        dt = _parse_ts(str(e.get("ts") or ""))
        if dt is None:
            continue
        if earliest is None or dt < earliest:
            earliest = dt
    return earliest


def meter_era_start() -> datetime | None:
    """llm-meter 第一条流水的北京时间；插件文件优先，账本回退。"""
    try:
        from .ingest_llm_meter import first_meter_datetime

        dt = first_meter_datetime()
        if dt is not None:
            return dt
    except Exception:
        _LOG.debug("usage first meter ts from plugin skipped", exc_info=True)
    return _first_meter_ts_from_ledger()


def bind_empty_meter_user_id(uid: str = "") -> int:
    """显式迁移：把无 user_id 流水归到指定账号（启动归户 / 运维调用）。

    禁止挂在个人用量 summarize/list 读路径上（否则先打开的账号永久抢走孤儿流水）。
    Token 口径不动。
    """
    want = str(uid or "").strip()
    if not want:
        return 0
    path = events_path()
    if not os.path.isfile(path):
        return 0
    changed = 0
    rewritten: list[str] = []
    try:
        with open(_lock_path(), "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                for evt in _iter_events():
                    if not str(evt.get("user_id") or "").strip():
                        evt = dict(evt)
                        evt["user_id"] = want[:80]
                        changed += 1
                    rewritten.append(json.dumps(evt, ensure_ascii=False))
                if changed:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("\n".join(rewritten) + ("\n" if rewritten else ""))
                        f.flush()
                        os.fsync(f.fileno())
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception:
        _LOG.warning("usage bind empty user_id failed", exc_info=True)
        return 0
    if changed:
        _LOG.info("usage: 已将 %d 条无账号流水归到 %s", changed, want)
    return changed


def supersede_pre_meter_side_lanes(*, since: datetime | str | None = None) -> int:
    """只删 meter 启用时刻起的 session/estimate 旁路，避免与 meter_* 双计。

    启用前的会话/记忆/标题必须保留。无 cutoff 则不删（宁漏双计，勿抹历史）。一次性（v2）。
    """
    marker = os.path.join(_dir(), ".meter_superseded_v3")
    if os.path.isfile(marker):
        return 0
    cutoff = as_shanghai(since) if since is not None else meter_era_start()
    if cutoff is None:
        try:
            os.makedirs(_dir(), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                f.write("removed=0\nreason=no_meter_ts\n")
        except OSError:
            pass
        return 0

    def _pred(e: dict[str, Any]) -> bool:
        if str(e.get("lane") or "").strip() not in _METER_SUPERSEDE_LANES:
            return False
        if str(e.get("quality") or "").strip() not in _METER_SUPERSEDE_QUALITY:
            return False
        if str(e.get("job_id") or "").startswith("meter_"):
            return False
        dt = _parse_ts(str(e.get("ts") or ""))
        if dt is None:
            return False
        return dt.replace(microsecond=0) >= cutoff.replace(microsecond=0)

    n = drop_events_where(_pred)
    try:
        os.makedirs(_dir(), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(f"removed={n}\nsince={cutoff.isoformat()}\n")
    except OSError:
        pass
    if n:
        _LOG.info(
            "usage: meter 启用后已清除 %d 条旁路流水（>= %s）以免双计",
            n,
            cutoff.isoformat(),
        )
    return n


def repair_meter_reasoning_in_total() -> int:
    """把误加 reasoning 的 total 改回官网口径（prompt+completion+cache）。可重复执行。"""
    path = events_path()
    if not os.path.isfile(path):
        return 0
    changed = 0
    rewritten: list[str] = []
    try:
        with open(_lock_path(), "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                for evt in _iter_events():
                    jid = str(evt.get("job_id") or "")
                    lane = str(evt.get("lane") or "")
                    if jid.startswith("meter_") or lane.startswith("dsh_"):
                        p = int(evt.get("prompt_tokens") or 0)
                        c = int(evt.get("completion_tokens") or 0)
                        cr = int(evt.get("cache_read_tokens") or 0)
                        cw = int(evt.get("cache_write_tokens") or 0)
                        r = int(evt.get("reasoning_tokens") or 0)
                        t = int(evt.get("total_tokens") or 0)
                        base = p + c + cr + cw
                        if r > 0 and t == base + r:
                            evt = dict(evt)
                            evt["total_tokens"] = base
                            changed += 1
                    rewritten.append(json.dumps(evt, ensure_ascii=False))
                if changed:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("\n".join(rewritten) + ("\n" if rewritten else ""))
                        f.flush()
                        os.fsync(f.fileno())
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception:
        _LOG.warning("usage align meter total to console口径 failed", exc_info=True)
        return 0
    if changed:
        _LOG.info("usage: 已将 %d 条流水 total 改为官网口径（不再另加 reasoning）", changed)
    return changed


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
    user_id: str | None = None,
    allow_active_fallback: bool = True,
) -> dict[str, Any] | None:
    """写一条流水。失败吞掉并打日志。ts 可回填历史 Job 时间。

    user_id 显式传入时优先生效（含空串）；否则走 ContextVar /（可选）active.json。
    """
    try:
        now = _parse_ts(ts) if ts else None
        if now is None:
            now = _now()
        body = missing_tokens() if not tokens else dict(tokens)
        if user_id is not None:
            uid = str(user_id).strip()[:80]
        else:
            # 只认 ContextVar /（可选）active；禁止静默归到种子账号（多账号会错挂）
            uid = _current_user_id(allow_active_fallback=allow_active_fallback)[:80]
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
            "user_id": uid,
            "machine_id": "",
            "reported_at": None,
        }
        try:
            from .machine import get_machine_id

            evt["machine_id"] = get_machine_id()[:80]
        except Exception:
            pass
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


def as_shanghai(value: datetime | str | None) -> datetime | None:
    """把 datetime / ISO 串转到北京时间；非法则 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ)
        return dt.astimezone(_TZ)
    return _parse_ts(str(value))


def exclude_at_or_after_cutoff(ts: str | None, cutoff: datetime | None) -> bool:
    """补采过滤：cutoff 之后（含同一秒）跳过。无时间戳则跳过，避免与 meter 双计。"""
    if cutoff is None:
        return False
    dt = _parse_ts(str(ts or ""))
    if dt is None:
        return True
    return dt.replace(microsecond=0) >= cutoff.replace(microsecond=0)


def _event_ymd(evt: dict[str, Any]) -> str:
    """流水所属北京时间自然日。禁止用 UTC 串的 [:10] 错日。"""
    dt = _parse_ts(str(evt.get("ts") or ""))
    if dt is not None:
        return dt.strftime("%Y-%m-%d")
    return str(evt.get("ts") or "")[:10]


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


def iter_all_events() -> list[dict[str, Any]]:
    """本机用量账本全部流水（企业管理视图与 hub 合并用）。"""
    return list(_iter_events())


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
    return drop_events_where(lambda e: str(e.get("job_id") or "").strip() == jid)


def drop_events_where(pred) -> int:
    """按谓词删除流水；返回删除条数。"""
    path = events_path()
    if not os.path.isfile(path):
        return 0
    kept: list[str] = []
    removed = 0
    for evt in _iter_events():
        try:
            hit = bool(pred(evt))
        except Exception:
            hit = False
        if hit:
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


def drop_events_by_lanes(lanes: set[str] | list[str]) -> int:
    """删除指定 lane 的流水（旁路补采升级估算时用）。"""
    want = {str(x).strip() for x in (lanes or []) if str(x).strip()}
    if not want:
        return 0
    return drop_events_where(lambda e: str(e.get("lane") or "").strip() in want)


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
    """拆成命中/未命中/输出；合计=三档之和，与 DeepSeek 控制台 Tokens 口径一致。

    reasoning 只作明细字段，不并进「输出」、不另加进合计（官网 completion 已含思考量）。
    LOCKED 2026-09-17：未经用户明确允许不得改本函数口径。
    """
    prompt = int(evt.get("prompt_tokens") or 0)
    hit = int(evt.get("cache_read_tokens") or 0)
    output = int(evt.get("completion_tokens") or 0)
    stored = int(evt.get("total_tokens") or 0)
    jid = str(evt.get("job_id") or "")
    lane = str(evt.get("lane") or "")
    exclusive = prompt + output + hit
    # DSH TokenUsage / meter / Cursor：input 与 cacheRead 互斥分列 → miss=prompt
    exclusive_shape = (
        hit > prompt
        or (hit and stored and abs(exclusive - stored) <= 2)
        or jid.startswith("meter_")
        or lane.startswith("dsh_")
    )
    if exclusive_shape:
        miss = prompt
    else:
        miss = max(0, prompt - hit) if prompt else 0
        if prompt == 0 and output == 0 and stored:
            miss = stored
    stack = miss + hit + output
    tokens = stack if stack > 0 else stored
    return {
        "tokens": tokens,
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


def summarize(*, days: int = 7, source: str = "", on: str = "", user_id: str | None = None, grain: str = "day") -> dict[str, Any]:
    """按北京时间汇总。

    grain=day（默认）：卡片与 hourly 锚定 on 当日；monthly 为该日所在自然月。
    grain=month：卡片为整月合计；hourly 为当月各小时跨日累加；daily/monthly 为当月逐日。
    user_id 非空时只统计该账号流水（用量跟账号，不跟设备）。
    """
    try:
        from .ingest_cursor import ingest_dsh_cursor_jobs

        ingest_dsh_cursor_jobs()
    except Exception:
        _LOG.warning("usage ingest dsh cursor failed", exc_info=True)
    meter_on = False
    meter_since: datetime | None = None
    try:
        from .ingest_llm_meter import ingest_llm_meter, meter_active, first_meter_datetime

        meter_on = bool(meter_active())
        ingest_llm_meter()
        if meter_on:
            meter_since = first_meter_datetime() or _first_meter_ts_from_ledger()
            supersede_pre_meter_side_lanes(since=meter_since)
        repair_meter_reasoning_in_total()
    except Exception:
        _LOG.warning("usage ingest llm-meter failed", exc_info=True)
    # meter 启用后仍补采「启用前」的 session/memory/title；启用后以 meter 为准，避免双计
    try:
        from .ingest_dsh_llm import ingest_dsh_sessions

        if not meter_on:
            ingest_dsh_sessions()
        elif meter_since is not None:
            ingest_dsh_sessions(before=meter_since)
    except Exception:
        _LOG.warning("usage ingest dsh sessions failed", exc_info=True)
    try:
        from .ingest_dsh_side import ingest_dsh_side_channels

        if not meter_on:
            ingest_dsh_side_channels()
        elif meter_since is not None:
            ingest_dsh_side_channels(before=meter_since)
    except Exception:
        _LOG.warning("usage ingest dsh side channels failed", exc_info=True)
    try:
        from .report import flush_report

        flush_report(force=False)
    except Exception:
        _LOG.warning("usage report flush failed", exc_info=True)
    grain = grain if grain in {"day", "month"} else "day"
    days = max(1, min(int(days or 7), 90))
    focus = _focus_day(on)
    m_start, m_end = _month_span(focus)
    if grain == "month":
        start, end = m_start, m_end
    else:
        end = focus + timedelta(days=1)
        start = end - timedelta(days=days)
    uid = None if user_id is None else str(user_id).strip()
    events = [e for e in _iter_events() if _in_range(e, start, end)]
    if uid is not None:
        events = [e for e in events if _match_user(e, uid)]
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
        slot["tokens"] += _event_parts(evt)["tokens"]
        mslot = models[src].setdefault(
            model,
            {**_empty_parts(), "model": model, "provider": str(evt.get("provider") or "")},
        )
        _add_parts(mslot, evt)
        day = _event_ymd(evt)
        dslot = daily.setdefault(day, _empty_day())
        _add_day_parts(dslot, evt, src)
        # 按日：只累加锚定日；按月：当月各日同时段累加
        if grain == "month" or day == today_key:
            _add_day_parts(hourly[_hour_of(evt)], evt, src)

    day_rows = []
    cur = start
    while cur < end:
        key = cur.strftime("%Y-%m-%d")
        row = daily.get(key) or _empty_day()
        day_rows.append({"date": key, **row})
        cur += timedelta(days=1)

    hour_rows = [{"hour": h, **hourly[h]} for h in range(24)]

    if grain == "month":
        month_rows = list(day_rows)
        monthly_map = daily
    else:
        monthly_map = {}
        for evt in _iter_events():
            if uid is not None and not _match_user(evt, uid):
                continue
            if source in {"llm", "cursor"} and evt.get("source") != source:
                continue
            if not _in_range(evt, m_start, m_end):
                continue
            src = evt.get("source") if evt.get("source") in {"llm", "cursor"} else "llm"
            day = _event_ymd(evt)
            _add_day_parts(monthly_map.setdefault(day, _empty_day()), evt, src)
        month_rows = []
        cur_m = m_start
        while cur_m < m_end:
            key = cur_m.strftime("%Y-%m-%d")
            month_rows.append({"date": key, **(monthly_map.get(key) or _empty_day())})
            cur_m += timedelta(days=1)

    if grain == "month":
        period = _empty_day()
        for row in month_rows:
            for k, v in row.items():
                if k == "date":
                    continue
                period[k] = int(period.get(k) or 0) + int(v or 0)
        today_row = period
    else:
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
        "days": days if grain == "day" else (m_end - m_start).days,
        "grain": grain,
        "from": start.strftime("%Y-%m-%d"),
        "to": (end - timedelta(seconds=1)).strftime("%Y-%m-%d"),
        "tz": "Asia/Shanghai",
        "on": today_key,
        "month": m_start.strftime("%Y-%m"),
        "month_from": m_start.strftime("%Y-%m-%d"),
        "month_to": (m_end - timedelta(seconds=1)).strftime("%Y-%m-%d"),
        "user_id": uid or "",
        "llm_meter_active": bool(meter_on),
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
    user_id: str | None = None,
) -> dict[str, Any]:
    uid = None if user_id is None else str(user_id).strip()
    rows = _iter_events()
    if uid is not None:
        rows = [e for e in rows if _match_user(e, uid)]
    if source in {"llm", "cursor"}:
        rows = [e for e in rows if e.get("source") == source]
    day = str(on or "").strip()[:10]
    if len(day) == 10 and day[4] == "-" and day[7] == "-":
        rows = [e for e in rows if _event_ymd(e) == day]
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
        "user_id": uid or "",
    }


def pending_report_events(*, limit: int = 200) -> list[dict[str, Any]]:
    """待上报：有 user_id 且尚未标 reported_at。按 id 升序，单批上限。"""
    lim = max(1, min(int(limit or 200), 500))
    out: list[dict[str, Any]] = []
    for evt in _iter_events():
        uid = str(evt.get("user_id") or "").strip()
        if not uid:
            continue
        if evt.get("reported_at"):
            continue
        eid = str(evt.get("id") or "").strip()
        if not eid:
            continue
        out.append(dict(evt))
    out.sort(key=lambda e: str(e.get("id") or ""))
    return out[:lim]


def mark_reported(event_ids: list[str], *, when: str) -> int:
    """把指定 id 标为已上报。返回实际改写条数。"""
    want = {str(x).strip() for x in (event_ids or []) if str(x).strip()}
    if not want:
        return 0
    path = events_path()
    if not os.path.isfile(path):
        return 0
    changed = 0
    lines: list[str] = []
    for evt in _iter_events():
        eid = str(evt.get("id") or "").strip()
        if eid in want and not evt.get("reported_at"):
            row = dict(evt)
            row["reported_at"] = when
            lines.append(json.dumps(row, ensure_ascii=False))
            changed += 1
        else:
            lines.append(json.dumps(evt, ensure_ascii=False))
    if not changed:
        return 0
    os.makedirs(_dir(), exist_ok=True)
    with open(_lock_path(), "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
                f.flush()
                os.fsync(f.fileno())
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    return changed


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
