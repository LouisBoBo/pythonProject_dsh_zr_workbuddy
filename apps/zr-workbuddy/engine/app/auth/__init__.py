"""本机账号：用户库、会话 JWT、当前登录用户（供用量 user_id）。

不挡聊天 / 写码 / 配置；未登录时流水 user_id 为空。
"""

from .active import clear_active, get_active_user, set_active
from .context import (
    current_user,
    current_user_id,
    reset_current_user,
    set_current_user,
)
from .tokens import issue_token, verify_token
from .users import ensure_seed_users, public_user, verify_password

__all__ = [
    "clear_active",
    "current_user",
    "current_user_id",
    "ensure_seed_users",
    "get_active_user",
    "issue_token",
    "public_user",
    "reset_current_user",
    "set_active",
    "set_current_user",
    "verify_password",
    "verify_token",
]
