"""按插件增量部署（P1）：人确认后 SSH/rsync 选定单元。"""
from .chat_bridge import handle_chat_code_deploy
from .config import availability, get_config
from .intent import is_code_deploy_question
from .ops import FEATURE_ID, confirm, get_job, prepare, status

__all__ = [
    "FEATURE_ID",
    "availability",
    "confirm",
    "get_config",
    "get_job",
    "handle_chat_code_deploy",
    "is_code_deploy_question",
    "prepare",
    "status",
]
