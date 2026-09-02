"""面板 chat 对接本机写码：需求收集 → 选项/确认卡（对齐 simplified）；确认后才开工。"""
from __future__ import annotations

from typing import Any

from .. import plugins_store
from .brief import (
    CodeDevBrief,
    append_sync_mismatch_warning,
    build_requirement,
    infer_target_from_text,
    is_options_confirm_message,
    merge_brief,
    ready_to_propose,
    validate_requirement_for_start,
    write_scope_from_hints,
)
from .config import availability, get_config
from .discuss import discuss_requirement
from .intent import extract_workspace_path
from .ops import FEATURE_ID, start as code_dev_start


def _base(**extra: Any) -> dict[str, Any]:
    out = {
        "ok": True,
        "thinking": "",
        "reply": "",
        "chart": None,
        "table": None,
        "note": None,
        "source": "code_dev",
        "data_source": "code_dev",
        "intent": {"type": "code_dev", "metric": "", "dim": None, "chart": None},
        "code_dev_ui": None,
        "job_id": None,
        "code_dev_brief": None,
    }
    out.update(extra)
    return out


def _enrich_propose_ui(
    ui: dict[str, Any],
    *,
    brief,
    llm_requirement: str = "",
) -> dict[str, Any]:
    """确认卡：canonical 需求 + 目标提示 + 校验结果。"""
    req = build_requirement(brief, llm_requirement)
    validation = validate_requirement_for_start(brief, req)
    hints = validation.get("target_hints") or {}

    prop = dict(ui.get("propose") or {})
    prop["requirement"] = req
    prop["original_goal"] = brief.original_goal
    prop["target_module"] = hints.get("module") or ""
    prop["expected_paths"] = hints.get("expected_paths") or []

    ui = {
        **ui,
        "kind": "propose",
        "requirement": req,
        "propose": prop,
        "brief": brief.to_dict(),
        "target_hints": hints,
        "validation": {
            "ok": validation.get("ok"),
            "errors": validation.get("errors") or [],
            "warnings": validation.get("warnings") or [],
        },
    }
    return ui


async def handle_chat_code_dev(
    text: str,
    *,
    client_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """异步：讨论需求，返回 thinking + 选项卡或确认卡；绝不在此直接 start Job。"""
    raw = (text or "").strip()
    if not plugins_store.is_enabled(FEATURE_ID):
        hint = plugins_store.disabled_hint(FEATURE_ID, capability="本机 Cursor 写码")
        return _base(reply=hint, note="code-dev 未启用", source="disabled")

    cfg = get_config()
    avail = availability()
    if not avail.get("ok"):
        return _base(
            reply=(
                "您这是在提「写码/改界面」需求。本机 Cursor 写码尚未就绪：\n\n"
                f"• {avail.get('detail') or '未就绪'}\n\n"
                "请打开引擎 **配置中心 → 写码车道**：勾选开启、填写 Cursor API Key 并保存，"
                "再发工程路径与需求。"
            ),
            note=avail.get("detail"),
            thinking="检查写码车道配置是否就绪。",
        )

    is_opt_confirm = is_options_confirm_message(raw)
    workspace = extract_workspace_path(raw) or (cfg.default_workspace or "").strip()
    brief = merge_brief(client_brief, raw, workspace=workspace)

    if not workspace and not is_opt_confirm:
        return _base(
            thinking="已识别写码意图，但缺少本机工程路径，需用户补充。",
            reply=(
                "已识别为**本机写码**需求。\n\n"
                "请先提供**工程绝对路径**（或到配置中心填写「常用本机工程路径」），例如：\n"
                f"`在 /Users/你/项目 开发：{raw[:80]}`\n\n"
                "收到路径后，我会先帮您**梳理需求并弹出确认卡**，确认后才会启动 Cursor 写码。"
            ),
            note="缺少 workspace",
            code_dev_brief=brief.to_dict(),
        )

    # 信息已够：跳过 LLM 轮询，直接出确认卡
    if is_opt_confirm and ready_to_propose(brief):
        ws = brief.workspace or workspace
        ui = _enrich_propose_ui(
            {
                "kind": "propose",
                "workspace": ws,
                "requirement": "",
                "target": "local",
                "propose": {"target": "local", "workspace": ws},
            },
            brief=brief,
        )
        return _base(
            thinking="已根据原始诉求与勾选整理写码确认卡；请核对目标模块与需求摘要后再开工。",
            reply="需求已明确。请核对下方**原始诉求**与**目标模块**，确认后才会启动 Cursor 写码。",
            code_dev_ui=ui,
            code_dev_brief=brief.to_dict(),
            intent={"type": "code_dev", "metric": "propose", "dim": None, "chart": None},
        )

    disc = await discuss_requirement(
        raw,
        workspace=workspace,
        is_options_confirm=is_opt_confirm,
        brief=brief,
    )
    if not disc.get("ok"):
        return _base(
            thinking=disc.get("thinking") or "",
            reply=disc.get("reply") or "需求梳理失败",
            note=disc.get("detail"),
            code_dev_brief=brief.to_dict(),
        )

    ui = None
    if disc.get("options"):
        opts = disc["options"]
        # 产品级：备注必填时前端强制；后端标记
        if brief.option_rounds >= 1 and not brief.original_goal:
            opts = {**opts, "notes_required": True, "notes_placeholder": "请写明业务模块、页面名称、接口路径（必填）"}
        elif brief.option_rounds >= 2:
            opts = {**opts, "notes_required": True, "notes_placeholder": "请补充页面路径、接口路径与验收点（必填）"}
        ui = {
            "kind": "options",
            "workspace": brief.workspace or workspace,
            "options": opts,
            "brief": brief.to_dict(),
            "original_goal": brief.original_goal,
        }
    elif disc.get("propose"):
        prop = disc["propose"]
        ui = {
            "kind": "propose",
            "workspace": str(prop.get("workspace") or brief.workspace or workspace or "").strip(),
            "requirement": str(prop.get("requirement") or "").strip(),
            "target": str(prop.get("target") or "local"),
            "propose": prop,
        }
        ui = _enrich_propose_ui(ui, brief=brief, llm_requirement=ui.get("requirement") or "")

    if not ui and (brief.workspace or workspace):
        ui = _enrich_propose_ui(
            {
                "kind": "propose",
                "workspace": brief.workspace or workspace,
                "requirement": brief.original_goal or raw,
                "target": "local",
                "propose": {
                    "target": "local",
                    "workspace": brief.workspace or workspace,
                    "requirement": brief.original_goal or raw,
                },
            },
            brief=brief,
            llm_requirement=disc.get("reply") or "",
        )
        note = "propose_fallback"
    else:
        note = disc.get("detail")

    intent = {"type": "code_dev", "metric": "", "dim": None, "chart": None}
    if ui and ui.get("kind"):
        intent = {**intent, "metric": str(ui.get("kind"))}

    return _base(
        thinking=disc.get("thinking") or "",
        reply=disc.get("reply") or "",
        note=note,
        code_dev_ui=ui,
        code_dev_brief=brief.to_dict(),
        intent=intent,
    )


def confirm_and_start(
    *,
    workspace: str,
    requirement: str,
    client_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """用户点确认卡后调用：真正启动 Job。"""
    ws = (workspace or "").strip()
    req = (requirement or "").strip()[:12000]
    if not ws:
        return {"ok": False, "detail": "workspace 不能为空", "reply": "请填写本机工程绝对路径"}
    if not req:
        return {"ok": False, "detail": "requirement 不能为空", "reply": "请填写需求摘要"}

    brief = CodeDevBrief.from_dict(client_brief)
    if ws:
        brief.workspace = ws
    validation = validate_requirement_for_start(brief, req)
    if not validation.get("ok"):
        err = "；".join(validation.get("errors") or ["需求校验未通过"])
        return {"ok": False, "detail": err, "reply": err, "validation": validation}

    hints = dict(validation.get("target_hints") or {})
    # 以需求正文复验模块，避免空 brief 绕过 write_scope
    hint2 = infer_target_from_text(brief.original_goal, req)
    if hint2.get("module") and (
        not hints.get("module")
        or hint2.get("confidence") == "high"
    ):
        hints = hint2
    scope = write_scope_from_hints(hints)

    out = code_dev_start(
        workspace=ws,
        message=req,
        write_scope=scope or None,
        brief=brief.to_dict(),
        target_hints=hints,
    )
    job_id = out.get("job_id") or ""
    if out.get("ok"):
        scope_note = f"\n• 同步范围：已限制在 {hints.get('module') or '目标模块'} 相关路径" if scope else ""
        reply = (
            f"已按您的确认启动本机写码任务 **{job_id}**。\n\n"
            f"• 工程：`{ws}`\n"
            f"• 目标模块：{hints.get('module') or '（请自行核对）'}\n"
            f"• 需求：{req[:300]}{scope_note}\n\n"
            "可用 `code-dev-job` / `mes_code_dev_job` 查询进度；成功后同步回目录（不会自动 commit）。"
        )
    else:
        reply = f"启动失败：{out.get('detail') or out.get('reply') or '未知错误'}"
    return {
        "ok": bool(out.get("ok")),
        "reply": reply,
        "detail": out.get("detail"),
        "job_id": job_id or None,
        "job": out.get("job"),
        "data_source": "code_dev",
        "validation": validation,
    }
