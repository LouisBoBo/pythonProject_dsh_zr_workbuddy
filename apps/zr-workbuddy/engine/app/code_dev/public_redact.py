"""P1 对外脱敏：只改返回副本，不改 job 落盘。"""
from __future__ import annotations

from typing import Any

from ..space.redact import redact_text

_TEXT_KEYS = (
    "live_text",
    "delivery_text",
    "thinking_text",
    "progress",
    "error",
    "current_action",
    "runtime_hint",
    "requirement",
    "message",
)

# 对外副本禁止回显的能力票据 / 密钥类字段
_STRIP_KEYS = ("stream_token",)


def _redact_str(val: Any, *, max_chars: int) -> Any:
    if val is None:
        return None
    if not isinstance(val, (dict, list)):
        s, _ = redact_text(str(val), max_chars=max_chars)
        return s
    return val


def _redact_messages(messages: Any) -> Any:
    if not isinstance(messages, list):
        return messages
    out = []
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        m2 = dict(m)
        if "content" in m2 and m2["content"] is not None:
            m2["content"] = _redact_str(m2["content"], max_chars=40_000)
        out.append(m2)
    return out


def _redact_brief(brief: Any) -> Any:
    if not isinstance(brief, dict):
        return brief
    b2 = dict(brief)
    for k in ("original_goal", "summary", "goal", "notes", "detail"):
        if k in b2 and b2[k] is not None:
            b2[k] = _redact_str(b2[k], max_chars=20_000)
    return b2


def redact_job_public(job: dict[str, Any] | None) -> dict[str, Any]:
    """返回脱敏后的 job 副本（含 events / 需求字段；剥掉 stream_token）。"""
    if not isinstance(job, dict):
        return {}
    out = dict(job)
    for k in _STRIP_KEYS:
        out.pop(k, None)
    for k in _TEXT_KEYS:
        if k in out and out[k] is not None:
            out[k] = _redact_str(out[k], max_chars=120_000)
    if "messages" in out:
        out["messages"] = _redact_messages(out.get("messages"))
    if "brief" in out:
        out["brief"] = _redact_brief(out.get("brief"))
    events = out.get("events")
    if isinstance(events, list):
        cleaned = []
        for ev in events:
            if not isinstance(ev, dict):
                cleaned.append(ev)
                continue
            e2 = dict(ev)
            for tk in ("text", "detail", "message", "title"):
                if tk in e2 and e2[tk] is not None:
                    e2[tk] = _redact_str(e2[tk], max_chars=20_000)
            cleaned.append(e2)
        out["events"] = cleaned
    return out


def redact_sse_payload(ev: dict[str, Any]) -> dict[str, Any]:
    """SSE 单条事件脱敏。"""
    if not isinstance(ev, dict):
        return {}
    out = dict(ev)
    for tk in ("text", "detail", "message", "title", "reply", "error"):
        if tk in out and out[tk] is not None and not isinstance(out[tk], (dict, list)):
            out[tk] = _redact_str(out[tk], max_chars=20_000)
    if isinstance(out.get("job"), dict):
        out["job"] = redact_job_public(out["job"])
    return out
