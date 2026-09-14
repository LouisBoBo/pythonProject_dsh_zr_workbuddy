"""把供应商 / SDK 的 usage 规范成本仓流水字段。"""
from __future__ import annotations

from typing import Any


def _int(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


def _get(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if obj is not None and hasattr(obj, name):
            v = getattr(obj, name)
            if v is not None:
                return v
    return None


def from_openai_usage(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    prompt = _int(raw.get("prompt_tokens"))
    completion = _int(raw.get("completion_tokens"))
    total = _int(raw.get("total_tokens")) or (prompt + completion)
    cache_read = _int(raw.get("prompt_cache_hit_tokens") or raw.get("cache_read_tokens"))
    details_p = raw.get("prompt_tokens_details")
    if cache_read == 0 and isinstance(details_p, dict):
        cache_read = _int(details_p.get("cached_tokens"))
    reasoning = 0
    details = raw.get("completion_tokens_details")
    if isinstance(details, dict):
        reasoning = _int(details.get("reasoning_tokens"))
    if prompt == 0 and completion == 0 and total == 0:
        return None
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": 0,
        "reasoning_tokens": reasoning,
        "total_tokens": total or (prompt + completion),
        "quality": "provider",
    }


def from_sdk_usage(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    prompt = _int(_get(raw, "input_tokens", "prompt_tokens", "inputTokens"))
    completion = _int(_get(raw, "output_tokens", "completion_tokens", "outputTokens"))
    total = _int(_get(raw, "total_tokens", "totalTokens"))
    cache_read = _int(_get(raw, "cache_read_tokens", "cacheReadTokens"))
    cache_write = _int(_get(raw, "cache_write_tokens", "cacheWriteTokens"))
    reasoning = _int(_get(raw, "reasoning_tokens", "reasoningTokens"))
    if total <= 0:
        total = prompt + completion + cache_read + cache_write + reasoning
    if total <= 0:
        return None
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "reasoning_tokens": reasoning,
        "total_tokens": total,
        "quality": "sdk",
    }


def missing_tokens() -> dict[str, Any]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "quality": "missing",
    }
