"""对话意图：本机审码（非 Git、非写码）。"""
from __future__ import annotations

import re

from ..code_dev.intent import extract_workspace_path

_REVIEW_HIT = re.compile(
    r"("
    r"审码|审核代码|审查代码|代码审查|代码审核|"
    r"review\s*代码|code\s*review|"
    r"审一下代码|审下代码|帮我审|检查一下代码|检查代码|"
    r"看看代码有没有|代码有没有问题|代码有问题吗|"
    r"本机审码|目录审码"
    r")",
    re.I,
)

# 纯写码不应进审码
_CODE_DEV_STRONG = re.compile(
    r"(写码|改代码|改界面|开发.{0,8}(页面|菜单|功能)|做.{0,6}(页面|功能)|Cursor\s*写)",
    re.I,
)

_SCOPE_RE = re.compile(
    r"(?:scope|范围|子路径|目录)[:：\s]+([^\s，。；;]+)|"
    r"(frontend/[^\s，。；;]+|backend/[^\s，。；;]+|src/[^\s，。；;]+)",
    re.I,
)

_FOCUS_RE = re.compile(
    r"(?:重点|关注|看看有没有|检查有没有)[:：\s]*([^。；;\n]{2,80})",
    re.I,
)


def is_code_review_question(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if _REVIEW_HIT.search(raw):
        if _CODE_DEV_STRONG.search(raw) and not re.search(
            r"(审|review|审查|检查代码)",
            raw,
            re.I,
        ):
            return False
        return True
    # 「路径 + 审」短句
    if extract_workspace_path(raw) and re.search(r"(审|review|审查)", raw, re.I):
        return True
    return False


def extract_scope(text: str) -> str:
    raw = text or ""
    m = _SCOPE_RE.search(raw)
    if not m:
        return ""
    return (m.group(1) or m.group(2) or "").strip().strip("/")


def extract_focus(text: str) -> str:
    raw = text or ""
    m = _FOCUS_RE.search(raw)
    return (m.group(1) or "").strip() if m else ""
