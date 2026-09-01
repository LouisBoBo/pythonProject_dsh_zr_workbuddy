"""引擎状态快照 —— /api/status 与 CLI status 共用。"""

from __future__ import annotations

from typing import Any, Dict

from .config_store import load_config
from .demo_data import get_demo_store
from .health import check_net, llm_ready


def build_status(*, include_demo: bool = True) -> Dict[str, Any]:
    cfg = load_config()
    llm = cfg.get("deepseek") or {}
    mes = cfg.get("mes") or {}
    provider = (llm.get("provider") or "deepseek").lower()
    configured = llm_ready(cfg)
    hint = (
        "本地 Ollama"
        if provider == "ollama" and configured
        else "DeepSeek API"
        if provider == "deepseek" and configured
        else "未配置"
    )
    out: Dict[str, Any] = {
        "ok": True,
        "network": check_net(),
        "llm": {
            "configured": configured,
            "provider": provider,
            "model": llm.get("model") or "",
            "hint": hint,
        },
        "mes": {"configured": bool(mes.get("base_url")), "base_url": mes.get("base_url") or ""},
        "config_ready": bool(mes.get("base_url")),
    }
    if include_demo:
        out["demo"] = get_demo_store().summary()
    return out
