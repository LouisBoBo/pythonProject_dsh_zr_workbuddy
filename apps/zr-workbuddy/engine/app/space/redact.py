"""敏感内容轻量脱敏（空间档案；失败则原样截断，不抛）。"""
from __future__ import annotations

import re

_KEYISH = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|authorization)\s*[:=]\s*\S+"
)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}")
_SK = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")


def redact_text(text: str, *, max_chars: int = 65536) -> tuple[str, bool]:
    raw = text if isinstance(text, str) else str(text or "")
    out = _KEYISH.sub(r"\1=••••", raw)
    out = _BEARER.sub("Bearer ••••", out)
    out = _SK.sub("sk-••••", out)
    truncated = False
    lim = max(1024, int(max_chars or 65536))
    if len(out) > lim:
        out = out[:lim] + "\n\n…（已截断）"
        truncated = True
    return out, truncated
