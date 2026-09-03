"""面板 / 对话：识别「要改代码/做界面」类意图（与查数、PCB 分流）。"""
from __future__ import annotations

import re

# 明确写码/改界面/增量改功能；避免误伤纯查数（产量/良率/工单…）
_CODE_DEV_HIT = re.compile(
    r"("
    r"写码|改代码|改前端|改后端|改界面|改页面|"
    r"开发.{0,24}(界面|页面|菜单|模块|功能|系统|页|列表|详情)|"
    r"(界面|页面|菜单|模块|列表|详情|功能).{0,16}(开发|定制|实现|改|增加|新增|补齐|加上|添加)|"
    r"(增加|新增|加上|补齐|添加).{0,24}(界面|页面|菜单|模块|功能|接口|列表|详情|按钮|角标|已读)|"
    r"做(一个|个)?.{0,12}(界面|页面|菜单|页|功能)|"
    r"实现.{0,16}(界面|页面|菜单|功能|详情|已读)|"
    r"定制.{0,8}(界面|功能|页面)|"
    r"消息中心|"
    r"报表中心|工时报表|员工工时|"
    r"标记已读|未读(数|角标)?|"
    r"查看(消息)?详情|"
    r"Cursor\s*(写码|改码)|本机写码"
    r")",
    re.I,
)

_NOT_CODE = re.compile(
    r"(产量|良率|不良率|OEE|工单数|在制|再制品|缺陷|停机|达成率|"
    r"查(一下|询)?|多少个|对比|趋势|分析原因)",
    re.I,
)

# 本机审码话术（交给 code-review；禁止当写码需求收集）
_CODE_REVIEW_HIT = re.compile(
    r"(审码|审核代码|审查代码|代码审查|代码审核|code\s*review|"
    r"审一下代码|审下代码|检查一下代码|检查代码|本机审码|目录审码)",
    re.I,
)

_PATH_RE = re.compile(
    r"(/(?:Users|home|opt|var/www|data)[^\s，。；;]+|"
    r"[A-Za-z]:\\[^\s，。；;]+)",
)


def is_code_dev_question(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    # 选项卡 / 确认回灌（前端构造），必须继续走写码顾问
    if raw.startswith("【写码需求选项已确认】") or raw.startswith("【写码确认】"):
        return True
    if len(raw) < 4:
        return False
    # 「审核代码」等审码意图：即使夹带「功能/界面」字样也不进写码顾问
    if _CODE_REVIEW_HIT.search(raw):
        return False
    if not _CODE_DEV_HIT.search(raw):
        return False
    # 同时强查数且无「开发界面」类时，让给查数
    if _NOT_CODE.search(raw) and not re.search(
        r"(界面|页面|菜单|写码|改代码|消息中心|已读|详情|功能)",
        raw,
    ):
        return False
    return True


def extract_workspace_path(text: str) -> str:
    m = _PATH_RE.search(text or "")
    if not m:
        return ""
    return m.group(1).rstrip("。．，,；;）)」」\"'")
