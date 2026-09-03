"""部署意图识别。"""
from __future__ import annotations

import re

_DEPLOY_RE = re.compile(
    r"(部署到|发布到|部署上线|发布上线|发到预发|发到测试|部署预发|增量部署|"
    r"同步到预发|上线到预发|部署 staging|deploy\s+to|trigger\s+deploy|"
    r"自动化部署|开始部署|确认部署|帮我部署)",
    re.I,
)
_EXCLUDE_RE = re.compile(
    r"(部署工单|部署计划|设备部署|MES.?部署|提交代码|审核代码|写码|开发)",
    re.I,
)
_EXACT = {
    "部署",
    "发布",
    "上线",
    "部署一下",
    "帮我部署",
    "部署上线",
    "发布上线",
    "增量部署",
    "同步到预发",
}


def is_code_deploy_question(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 200:
        return False
    if _EXCLUDE_RE.search(t) and not re.search(
        r"部署到|发布到|部署上线|发布上线|deploy\s+to", t, re.I
    ):
        return False
    if t in _EXACT:
        return True
    return bool(_DEPLOY_RE.search(t))
