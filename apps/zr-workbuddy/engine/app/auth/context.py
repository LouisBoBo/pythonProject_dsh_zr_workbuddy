"""请求内当前用户（可选；主路径仍靠 active.json）。"""
from __future__ import annotations

import contextvars
from typing import Any

_user: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "auth_user", default=None
)


def set_current_user(user: dict[str, Any] | None) -> contextvars.Token:
    return _user.set(user)


def reset_current_user(token: contextvars.Token) -> None:
    _user.reset(token)


def current_user() -> dict[str, Any] | None:
    return _user.get()


def current_user_id() -> str:
    u = _user.get()
    if u and u.get("id"):
        return str(u["id"])
    return ""
