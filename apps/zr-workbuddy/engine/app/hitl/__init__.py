"""人机确认（HITL）票据：一次性 nonce / path_ticket。

企业级硬门禁：写码/提交/部署 confirm 与审码开跑须引擎可验证票据，
禁止仅信 Agent 参数 confirmed=true 或裸绝对路径。
"""
from __future__ import annotations

from .origin import (
    HITL_UI_HEADER,
    HITL_UI_HEADER_VALUE,
    issue_surface_ok,
    local_origin_ok,
    mutating_path_guarded,
)
from .tokens import (
    normalize_payload_hash,
    ACTION_COMMIT,
    ACTION_DEPLOY,
    ACTION_DEV,
    ACTION_PATH,
    HTTP_ISSUE_ACTIONS,
    attach_path_ticket,
    consume,
    gate_review_path,
    issue,
    issue_path_ticket,
    require_confirm_nonce,
    reset_store_for_tests,
)

__all__ = [
    "ACTION_COMMIT",
    "ACTION_DEPLOY",
    "ACTION_DEV",
    "ACTION_PATH",
    "HTTP_ISSUE_ACTIONS",
    "HITL_UI_HEADER",
    "HITL_UI_HEADER_VALUE",
    "attach_path_ticket",
    "consume",
    "gate_review_path",
    "issue",
    "issue_path_ticket",
    "issue_surface_ok",
    "local_origin_ok",
    "mutating_path_guarded",
    "normalize_payload_hash",
    "require_confirm_nonce",
    "reset_store_for_tests",
]
