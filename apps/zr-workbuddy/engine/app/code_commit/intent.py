"""对话意图：人触发提交（非纯审码 / 纯写码）。"""
from __future__ import annotations

import re

from ..code_dev.intent import extract_workspace_path

_COMMIT_HIT = re.compile(
    r"("
    r"提交代码|提交今天的代码|提交今日代码|提交本批代码|"
    r"帮我提交|请提交|git\s*commit|commit\s*(代码|一下)?|"
    r"推送代码|push\s*代码|提交并推送"
    r")",
    re.I,
)

# 门禁阻断后：对话修复 → 写码确认卡（闭环）
_FIX_FROM_GATE = re.compile(
    r"("
    r"【门禁阻断修复】|"
    r"修复这些问题|修复这些阻断|修复门禁|按门禁修复|按阻断修复|"
    r"修一下(提交|门禁|阻断)|修复(提交)?(批审|门禁)?(阻断|问题)|"
    r"把阻断修(好|掉|一下)|根据(提交)?门禁修(复|改)|"
    r"fix\s*(these\s*)?(findings|issues|blockers?)"
    r")",
    re.I,
)

_GATE_JOB_ID = re.compile(r"(?:job_id[=：:\s]+|任务[=：:\s]+)(cc-[a-zA-Z0-9]+)", re.I)

# 纯审码 / 纯写码不应进提交车道
_REVIEW_PURE = re.compile(
    r"(审码|审核代码|审查代码|代码审查|代码审核|code\s*review)",
    re.I,
)
_CODE_DEV_PURE = re.compile(
    r"(写码|改代码|改界面|开发.{0,8}(页面|菜单|功能)|做.{0,6}(页面|功能)|Cursor\s*写)",
    re.I,
)


def is_fix_from_gate_question(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(_FIX_FROM_GATE.search(raw))


def extract_gate_job_id(text: str) -> str:
    m = _GATE_JOB_ID.search(text or "")
    return m.group(1) if m else ""


def is_code_commit_question(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    # 修复闭环优先，避免「修复后提交」误入提交选目录
    if is_fix_from_gate_question(raw) and not re.search(
        r"^(提交代码|帮我提交|请提交)\b", raw
    ):
        return False
    if not _COMMIT_HIT.search(raw):
        # 「路径 + 提交」短句
        if extract_workspace_path(raw) and re.search(r"提交", raw):
            if _REVIEW_PURE.search(raw) and not re.search(r"提交|commit|push", raw, re.I):
                return False
            return True
        return False
    # 纯审码（无提交意图）
    if _REVIEW_PURE.search(raw) and not re.search(r"提交|commit|push", raw, re.I):
        return False
    # 纯写码且无提交意图
    if _CODE_DEV_PURE.search(raw) and not re.search(r"提交|commit|push", raw, re.I):
        return False
    return True


def extract_commit_workspace(text: str) -> str:
    return extract_workspace_path(text or "") or ""
