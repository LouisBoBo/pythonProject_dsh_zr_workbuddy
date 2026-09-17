"""只读补采 DSH 旁路 LLM（记忆整理 / 会话标题）——不改宿主/插件源码。

聊天步进已由 ingest_dsh_llm 覆盖；记忆 dream/summarize、会话标题 LLM
同样走 DeepSeek Key，但不会写入 session usage chunk。

记忆库 llm_audit_logs 的 token 字段经常为 0：此时按 DeepSeek 文档口径
（汉字≈0.6 / 其它字符≈0.3 token）对可见输入/输出文本做 **estimate**，
并在 quality 标明，禁止冒充 provider 真值。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .parse import missing_tokens
from .store import append_event, as_shanghai, drop_events_where, exclude_at_or_after_cutoff, known_job_ids

_LOG = logging.getLogger(__name__)
_last_ingest = 0.0
_refreshed_estimates = False


def _memory_db() -> Path:
    return Path.home() / ".dsh" / "memory" / "memory.db"


def _parse_audit_ts(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _to_dt(raw: Any) -> datetime | None:
    text = _parse_audit_ts(raw)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _estimate_tokens_from_text(text: str) -> int:
    """DeepSeek 文档近似：汉字≈0.6、其它≈0.3 token/字。"""
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            cjk += 1
        elif ch.isspace():
            continue
        else:
            other += 1
    return max(0, int(cjk * 0.6 + other * 0.3))


def _estimate_cjk_tokens(n_chars: int) -> int:
    return max(0, int(max(0, int(n_chars)) * 0.6))


def _estimate_parts(prompt_tokens: int, completion_tokens: int = 0) -> dict[str, Any]:
    prompt = max(0, int(prompt_tokens))
    completion = max(0, int(completion_tokens))
    total = prompt + completion
    if total <= 0:
        body = missing_tokens()
        body["quality"] = "missing"
        return body
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": total,
        "quality": "estimate",
    }


def _estimate_body(prompt_text: str, completion_text: str = "") -> dict[str, Any]:
    return _estimate_parts(
        _estimate_tokens_from_text(prompt_text),
        _estimate_tokens_from_text(completion_text),
    )


def _tokens_from_audit(row: dict[str, Any], *, estimate: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = int(row.get("input_tokens") or 0)
    completion = int(row.get("output_tokens") or 0)
    total = int(row.get("total_tokens") or 0) or (prompt + completion)
    if total > 0 or prompt > 0 or completion > 0:
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": total or (prompt + completion),
            "quality": "session",
        }
    if estimate and int(estimate.get("total_tokens") or 0) > 0:
        return estimate
    body = missing_tokens()
    body["quality"] = "missing"
    return body


def _lane_for_op(trigger: str, op: str) -> str:
    t = f"{trigger}:{op}".lower()
    if "title" in t:
        return "dsh_title"
    return "dsh_memory"


def _load_dream_rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    try:
        rows = cur.execute(
            "SELECT id, created_at, status, input_count, input, decisions, outcome, "
            "summary_stored FROM dream_runs"
        ).fetchall()
    except sqlite3.Error:
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "status": r["status"],
                "input_count": r["input_count"],
                "input": r["input"] or "",
                "decisions": r["decisions"] or "",
                "outcome": r["outcome"] or "",
                "summary_stored": r["summary_stored"] or "",
                "_dt": _to_dt(r["created_at"]),
            }
        )
    return out


def _memories_text(cur: sqlite3.Cursor, ids: list[str]) -> str:
    if not ids:
        return ""
    parts: list[str] = []
    for mid in ids[:80]:
        try:
            row = cur.execute(
                "SELECT title, content, COALESCE(_full_content, '') FROM memories WHERE id=?",
                (mid,),
            ).fetchone()
        except sqlite3.Error:
            continue
        if not row:
            continue
        parts.append(str(row[0] or ""))
        parts.append(str(row[2] or row[1] or ""))
    return "\n".join(parts)


def _estimate_for_audit(
    cur: sqlite3.Cursor,
    row: dict[str, Any],
    dreams: list[dict[str, Any]],
) -> dict[str, Any] | None:
    op = str(row.get("operation_type") or "").lower()
    trigger = str(row.get("trigger_source") or "").lower()
    dt = _to_dt(row.get("timestamp"))
    duration_ms = int(row.get("duration_ms") or 0)

    # dream_*：对齐 dream_runs（±120s）
    if "dream" in op or "dream" in trigger:
        best = None
        best_delta = 1e18
        if dt is not None:
            for dream in dreams:
                ddt = dream.get("_dt")
                if ddt is None:
                    continue
                delta = abs((ddt - dt).total_seconds())
                if delta < best_delta:
                    best_delta = delta
                    best = dream
        if best is not None and best_delta <= 120:
            prompt = str(best.get("input") or "")
            completion = "\n".join(
                [
                    str(best.get("decisions") or ""),
                    str(best.get("outcome") or ""),
                    str(best.get("summary_stored") or ""),
                ]
            )
            body = _estimate_body(prompt, completion)
            if int(body.get("total_tokens") or 0) > 0:
                return body
        # 无匹配：按时长给下限（避免次数涨了 token 仍为 0）
        floor_chars = 4000 if "consolidat" in op else 1200
        if duration_ms > 0:
            floor_chars = max(floor_chars, min(80_000, duration_ms // 8))
        return _estimate_parts(
            _estimate_cjk_tokens(floor_chars),
            _estimate_cjk_tokens(max(200, floor_chars // 20)),
        )

    # summarize：用 related_memory_ids 正文；否则按时长
    if "summar" in op or "summar" in trigger:
        ids_raw = row.get("related_memory_ids")
        ids: list[str] = []
        if isinstance(ids_raw, str) and ids_raw.strip():
            try:
                parsed = json.loads(ids_raw)
                if isinstance(parsed, list):
                    ids = [str(x) for x in parsed if x]
            except json.JSONDecodeError:
                pass
        elif isinstance(ids_raw, list):
            ids = [str(x) for x in ids_raw if x]
        text = _memories_text(cur, ids)
        if text.strip():
            # 摘要输出通常远小于输入
            out_chars = max(200, min(4000, len(text) // 8))
            return _estimate_body(text, "中" * out_chars)
        floor = 800
        if duration_ms > 0:
            floor = max(floor, min(40_000, duration_ms // 6))
        return _estimate_parts(
            _estimate_cjk_tokens(floor),
            _estimate_cjk_tokens(max(120, floor // 15)),
        )

    return None


def ingest_dsh_memory_audit(*, force: bool = False, before: datetime | str | None = None) -> int:
    """扫描 ~/.dsh/memory/memory.db 的 llm_audit_logs。"""
    global _last_ingest
    now = time.monotonic()
    if not force and now - _last_ingest < 2.0:
        return 0
    from . import store as st

    if not force and getattr(st, "_data_dir_override", None):
        return 0
    _last_ingest = now
    cutoff = as_shanghai(before)
    db = _memory_db()
    if not db.is_file():
        return 0
    known = known_job_ids()
    added = 0
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        try:
            rows = cur.execute(
                "SELECT id, timestamp, trigger_source, operation_type, model_id, "
                "input_tokens, output_tokens, total_tokens, status, error_message, "
                "duration_ms, related_memory_ids "
                "FROM llm_audit_logs ORDER BY id ASC"
            ).fetchall()
        except sqlite3.Error:
            # 旧表无 duration / related 列
            try:
                rows = cur.execute(
                    "SELECT id, timestamp, trigger_source, operation_type, model_id, "
                    "input_tokens, output_tokens, total_tokens, status, error_message "
                    "FROM llm_audit_logs ORDER BY id ASC"
                ).fetchall()
            except sqlite3.Error:
                _LOG.debug("memory llm_audit_logs unavailable", exc_info=True)
                con.close()
                return 0
        dreams = _load_dream_rows(cur)
        for row in rows:
            rid = int(row["id"] or 0)
            if rid <= 0:
                continue
            job_id = f"dsh-mem-audit:{rid}"
            if job_id in known:
                continue
            model_raw = str(row["model_id"] or "")
            provider, _, model = model_raw.partition(":")
            if not model:
                model = model_raw or "deepseek-v4-flash"
                provider = "deepseek"
            else:
                provider = provider or "deepseek"
            if "deepseek" in provider.lower():
                provider = "deepseek"
            trigger = str(row["trigger_source"] or "")
            op = str(row["operation_type"] or "")
            status = str(row["status"] or "").lower()
            ok = status in {"", "success", "ok", "succeeded"}
            row_d = dict(row)
            est = _estimate_for_audit(cur, row_d, dreams)
            tokens = _tokens_from_audit(row_d, estimate=est)
            ts = _parse_audit_ts(row["timestamp"])
            if exclude_at_or_after_cutoff(ts, cutoff):
                continue
            evt = append_event(
                source="llm",
                lane=_lane_for_op(trigger, op),
                provider=provider[:80],
                model=model[:120],
                tokens=tokens,
                ok=ok,
                job_id=job_id,
                error_class="" if ok else str(row["error_message"] or status)[:80],
                ts=ts or None,
            )
            if evt is not None:
                added += 1
                known.add(job_id)
        con.close()
    except Exception:
        _LOG.warning("ingest dsh memory audit failed", exc_info=True)
        return added
    if added:
        _LOG.info("ingested %s DSH memory LLM audit events", added)
    return added


def ingest_dsh_title_llm(*, force: bool = False, before: datetime | str | None = None) -> int:
    """扫描会话里的 session/title-llm-request；按 prompt 文本估算 token。"""
    from .ingest_dsh_llm import (
        _iter_lines,
        _iter_session_files,
        _session_id_from_path,
        _sessions_root,
        _ts_from_ms,
    )
    from . import store as st

    if not force and getattr(st, "_data_dir_override", None):
        return 0
    known = known_job_ids()
    added = 0
    cutoff = as_shanghai(before)
    root = _sessions_root()
    for path in _iter_session_files(root):
        sid = _session_id_from_path(path)
        try:
            for line in _iter_lines(path):
                if "title-llm-request" not in line and '"type":"session/title"' not in line.replace(
                    " ", ""
                ):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ = str(obj.get("type") or "")
                if typ not in {"session/title-llm-request", "session/title"}:
                    continue
                # 只在 request 记一次；title 结果用来补 completion 估算时需同 seq 合并太重，
                # request 上直接估 prompt + 短标题输出。
                if typ != "session/title-llm-request":
                    continue
                seq = obj.get("seq")
                job_id = f"dsh-title:{sid or 'x'}:s{seq}"
                if not sid or job_id in known:
                    continue
                data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
                route = data.get("route") if isinstance(data.get("route"), dict) else {}
                provider = str(route.get("provider") or "deepseek")
                if "deepseek" in provider.lower():
                    provider = "deepseek"
                model = str(route.get("model") or "deepseek-v4-flash")
                ts = _ts_from_ms(obj.get("time"))
                if exclude_at_or_after_cutoff(ts, cutoff):
                    continue
                prompt = "\n".join(
                    [
                        str(data.get("system") or ""),
                        str(data.get("prompt") or ""),
                        str(data.get("user") or ""),
                        json.dumps(data.get("messageSeqs") or [], ensure_ascii=False),
                    ]
                )
                tokens = _estimate_body(prompt, "会话标题示例")
                if int(tokens.get("total_tokens") or 0) <= 0:
                    tokens = _estimate_parts(_estimate_cjk_tokens(400), _estimate_cjk_tokens(20))
                evt = append_event(
                    source="llm",
                    lane="dsh_title",
                    provider=provider[:80],
                    model=model[:120],
                    tokens=tokens,
                    ok=True,
                    job_id=job_id,
                    ts=ts or None,
                )
                if evt is not None:
                    added += 1
                    known.add(job_id)
        except Exception:
            _LOG.debug("ingest title-llm failed path=%s", path, exc_info=True)
            continue
    if added:
        _LOG.info("ingested %s DSH session title LLM events", added)
    return added


def refresh_side_channel_estimates(*, force: bool = False, before: datetime | str | None = None) -> dict[str, int]:
    """删掉旁路 lane 后重采（把原先 token=0 的 missing 升为 estimate）。不碰 meter_*。"""
    global _refreshed_estimates
    if _refreshed_estimates and not force:
        return {"dropped": 0, "memory": 0, "title": 0}
    from . import store as st

    if not force and getattr(st, "_data_dir_override", None):
        return {"dropped": 0, "memory": 0, "title": 0}
    dropped = drop_events_where(
        lambda e: (
            str(e.get("lane") or "").strip() in {"dsh_memory", "dsh_title"}
            and not str(e.get("job_id") or "").startswith("meter_")
        )
    )
    mem = ingest_dsh_memory_audit(force=True, before=before)
    title = ingest_dsh_title_llm(force=True, before=before)
    _refreshed_estimates = True
    return {"dropped": dropped, "memory": mem, "title": title}


def ingest_dsh_side_channels(*, force: bool = False, before: datetime | str | None = None) -> dict[str, int]:
    """汇总旁路补采。首次（或 force）会刷新零 token 旁路估算。"""
    out: dict[str, int] = {"memory": 0, "title": 0, "dropped": 0}
    try:
        # 账本里若仍有旁路 token=0，做一次升级（meter 行除外）
        need_refresh = force
        if not need_refresh:
            from .store import _iter_events

            for e in _iter_events():
                if str(e.get("job_id") or "").startswith("meter_"):
                    continue
                if str(e.get("lane") or "") in {"dsh_memory", "dsh_title"} and int(
                    e.get("total_tokens") or 0
                ) <= 0:
                    need_refresh = True
                    break
        if need_refresh:
            refreshed = refresh_side_channel_estimates(force=True, before=before)
            out.update(refreshed)
            return out
        out["memory"] = ingest_dsh_memory_audit(force=force, before=before)
        out["title"] = ingest_dsh_title_llm(force=force, before=before)
    except Exception:
        _LOG.warning("ingest_dsh_side_channels failed", exc_info=True)
    return out
