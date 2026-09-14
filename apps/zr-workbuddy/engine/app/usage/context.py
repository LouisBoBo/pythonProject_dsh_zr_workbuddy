"""本机 token 用量账本：LLM 与 Cursor 写码流水。

记账失败不得影响主流程。密钥禁止写入流水。
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

_lane: contextvars.ContextVar[str] = contextvars.ContextVar("usage_lane", default="")
_job_id: contextvars.ContextVar[str] = contextvars.ContextVar("usage_job_id", default="")


def current_lane(default: str = "unknown") -> str:
    return (_lane.get() or "").strip() or default


def current_job_id() -> str:
    return (_job_id.get() or "").strip()


@contextmanager
def usage_scope(*, lane: str = "", job_id: str = "") -> Iterator[None]:
    t_lane = _lane.set(lane) if lane else None
    t_job = _job_id.set(job_id) if job_id else None
    try:
        yield
    finally:
        if t_job is not None:
            _job_id.reset(t_job)
        if t_lane is not None:
            _lane.reset(t_lane)
