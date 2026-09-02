"""写码需求讨论：先思考澄清，输出选项卡或确认卡；不落盘。"""
from __future__ import annotations

from typing import Any

from ..nl_engine import llm_freeform
from .fence import parse_machine_blocks

DISCUSS_SYSTEM = """你是 ZR-WorkBuddy 写码需求顾问。用户要在本机工程上改代码/做界面。
目标：少打字收集需求 → 输出机器块供前端确认 → **禁止声称已改代码**。

硬规则：
1. 正文最多 1～2 句中文（可含简短思考要点），然后立刻输出**一个**机器块。
2. 需求仍模糊时，只输出选项卡（禁止直接 propose）：
:::cursor_dev_options
{"title":"请确认写码关键项","summary":"勾选即可","notes_placeholder":"其它备注（可选）","groups":[{"id":"scope","label":"本轮范围","multi":true,"required":true,"options":[{"id":"a","label":"…"}]}]}
:::
3. 需求够开工时，只输出确认卡（默认本机）：
:::cursor_dev_propose
{"target":"local","workspace":"__WORKSPACE__","requirement":"完整需求摘要，含验收点"}
:::
4. 禁止同一轮同时输出 options 与 propose。
5. 已有工程目录时：不要问技术栈；选项聚焦本轮增量（菜单/页面/接口等）。
6. 用户消息若以「【写码需求选项已确认】」开头：根据勾选整理需求，尽量直接 propose。
7. workspace 字段必须填用户给出的绝对路径（见下方），不要留空。
8. 只输出中文正文 + 机器块，不要 Markdown 代码围栏包住机器块。
9. **requirement 必须逐字保留【原始诉求】中的业务名称**（如「员工工时报表」「报表中心菜单」），禁止改写成「通用列表页 CRUD」。
10. 若【原始诉求】已明确模块与功能，且用户已勾选范围：**直接 propose**，不要再出 options。
11. propose 的 requirement 须含：原始诉求、目标模块、菜单/路由、接口路径、验收点。
"""


def _user_payload(
    *,
    text: str,
    workspace: str,
    is_options_confirm: bool,
    brief=None,
) -> str:
    ws = (workspace or "").strip()
    tip = f"【本机工程绝对路径】{ws}\n" if ws else "【本机工程】尚未指定，propose.workspace 可留空由确认卡填写\n"
    head = "【写码需求选项已确认后续】\n" if is_options_confirm else "【用户写码诉求】\n"
    body = tip + head + (text or "").strip()
    if brief is not None:
        goal = (getattr(brief, "original_goal", None) or "").strip()
        rounds = int(getattr(brief, "option_rounds", 0) or 0)
        if goal:
            body += f"\n\n【原始诉求（禁止丢失或泛化）】{goal}"
        if rounds:
            body += f"\n【已确认选项轮数】{rounds}"
        for sel in getattr(brief, "selections", None) or []:
            lines = sel.get("lines") or []
            if lines:
                body += "\n【历史勾选】\n" + "\n".join(lines)
    return body


async def discuss_requirement(
    text: str,
    *,
    workspace: str = "",
    is_options_confirm: bool = False,
    brief=None,
) -> dict[str, Any]:
    """返回 {ok, thinking, reply, options, propose, detail}。"""
    llm_cfg = load_llm_cfg()
    if not llm_cfg:
        # 无 LLM：选项阶段给默认卡；选项已确认则直接出 propose，仍不自动开工
        if is_options_confirm:
            from .brief import CodeDevBrief, build_requirement

            b = brief if isinstance(brief, CodeDevBrief) else CodeDevBrief.from_dict(brief)
            req = build_requirement(b)
            propose = {
                "target": "local",
                "workspace": (workspace or b.workspace or "").strip(),
                "requirement": req or "按已确认选项完成本机写码",
            }
            return {
                "ok": True,
                "thinking": "未配置 LLM；已根据勾选整理写码确认卡，须用户确认后才启动。",
                "reply": "请核对工程路径与需求摘要，确认后才会用 Cursor 写入本机（不会自动 commit）。",
                "options": None,
                "propose": propose,
                "detail": "fallback_propose",
            }
        options = {
            "title": "请确认本轮写码范围",
            "summary": "当前未配置对话 LLM，请勾选后继续；确认后才会生成写码确认卡。",
            "notes_placeholder": "补充说明（可选）",
            "groups": [
                {
                    "id": "scope",
                    "label": "本轮要做哪些",
                    "multi": True,
                    "required": True,
                    "options": [
                        {"id": "menu", "label": "侧栏/导航增加入口"},
                        {"id": "page", "label": "新增或改列表/详情页"},
                        {"id": "api", "label": "配套接口"},
                        {"id": "other", "label": "其它（请在备注写清）"},
                    ],
                }
            ],
        }
        return {
            "ok": True,
            "thinking": "未配置 LLM，使用默认选项卡收集范围。",
            "reply": "请先勾选本轮要做的范围，确认后我会给出写码确认卡（不会立刻改代码）。",
            "options": options,
            "propose": None,
            "detail": "fallback_options",
        }

    system = DISCUSS_SYSTEM.replace("__WORKSPACE__", (workspace or "").strip() or "")
    raw = await llm_freeform(
        system,
        _user_payload(
            text=text,
            workspace=workspace,
            is_options_confirm=is_options_confirm,
            brief=brief,
        ),
        llm_cfg,
        max_tokens=2048,
        timeout=90,
        temperature=0.35,
    )
    if not raw:
        return {
            "ok": False,
            "thinking": "",
            "reply": "需求梳理失败（LLM 无响应）。请稍后重试，或检查配置中心 LLM。",
            "options": None,
            "propose": None,
            "detail": "llm_failed",
        }

    parsed = parse_machine_blocks(raw)
    prose = parsed.get("prose") or ""
    options = parsed.get("options")
    propose = parsed.get("propose")
    if propose and workspace and not str(propose.get("workspace") or "").strip():
        propose = {**propose, "workspace": workspace, "target": propose.get("target") or "local"}
    if propose and workspace:
        propose = {**propose, "workspace": str(propose.get("workspace") or workspace).strip() or workspace}

    thinking = "梳理用户写码意图与可勾选项/确认摘要。"
    if options:
        thinking = "需求尚有离散决策点，先用选项卡收集，确认后才能开工。"
    elif propose:
        thinking = "需求已较清晰，生成写码确认卡；须用户确认后才启动 Cursor Local。"

    if not options and not propose:
        # 模型没出机器块：兜底选项
        options = {
            "title": "请确认写码关键项",
            "summary": "模型未输出标准确认块，请勾选后继续。",
            "notes_placeholder": "其它备注（可选）",
            "groups": [
                {
                    "id": "scope",
                    "label": "本轮范围",
                    "multi": True,
                    "required": True,
                    "options": [
                        {"id": "ui", "label": "界面/菜单"},
                        {"id": "api", "label": "接口"},
                        {"id": "both", "label": "界面+接口"},
                    ],
                }
            ],
        }
        if not prose:
            prose = "请勾选本轮范围；确认后我会给出写码确认卡。"

    return {
        "ok": True,
        "thinking": thinking,
        "reply": prose or ("请确认下列选项。" if options else "请确认写码摘要后开始。"),
        "options": options,
        "propose": propose if not options else None,  # 同轮禁止双卡
        "detail": "options" if options else "propose",
        "raw": raw,
    }


def load_llm_cfg() -> dict | None:
    """复用引擎 deepseek 配置；不可用则 None。"""
    from ..config_store import load_config
    from ..health import llm_ready

    cfg = load_config()
    if not llm_ready(cfg):
        return None
    llm = cfg.get("deepseek") or {}
    if (llm.get("provider") or "").lower() == "none":
        return None
    return llm
