"""面板 chat：部署意图 → 确认卡（不自动 rsync）。"""
from __future__ import annotations

from typing import Any

from .. import plugins_store
from .config import availability, get_config
from .intent import is_code_deploy_question
from .ops import FEATURE_ID, prepare


def _base(**extra: Any) -> dict[str, Any]:
    out = {
        "ok": True,
        "thinking": "",
        "reply": "",
        "chart": None,
        "table": None,
        "note": None,
        "source": "code_deploy",
        "data_source": "code_deploy",
        "intent": {"type": "code_deploy", "metric": "confirm", "dim": None, "chart": None},
        "job_id": None,
        "code_deploy_ui": None,
    }
    out.update(extra)
    return out


async def handle_chat_code_deploy(text: str) -> dict[str, Any]:
    if not plugins_store.is_enabled(FEATURE_ID):
        hint = plugins_store.disabled_hint(FEATURE_ID, capability="按插件增量部署")
        return _base(
            reply=hint,
            note="code-deploy 未启用",
            intent={"type": "code_deploy", "metric": "disabled", "dim": None, "chart": None},
        )
    avail = availability()
    cfg = get_config()
    # prepare 可在 SSH 未齐时仍展示单元（can_deploy=false）
    out = prepare(cfg.default_workspace or "", env=cfg.default_env)
    if not out.get("ok") and not out.get("code_deploy_ui"):
        return _base(
            reply=out.get("reply") or out.get("detail") or "无法准备部署",
            note="prepare_failed",
            intent={"type": "code_deploy", "metric": "blocked", "dim": None, "chart": None},
        )
    ui = out.get("code_deploy_ui")
    reply = out.get("reply") or ""
    if not avail.get("ok"):
        reply = (reply + "\n\n" if reply else "") + str(avail.get("detail") or "")
    return _base(
        reply=reply,
        job_id=out.get("job_id"),
        note="code_deploy.confirm",
        code_deploy_ui=ui,
        intent={"type": "code_deploy", "metric": "confirm", "dim": None, "chart": None},
    )


__all__ = [
    "handle_chat_code_deploy",
    "is_code_deploy_question",
]
