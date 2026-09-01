"""网络与 LLM 就绪探测（供 main / cli_ops 共用，避免循环依赖）。"""

from __future__ import annotations

import socket

_net_ok = None
_net_at = 0.0


def check_net() -> bool:
    """探测外网（DeepSeek API 是否可达）；每 60 秒重试，不永久缓存。"""
    global _net_ok, _net_at
    import time
    if _net_ok is None or time.time() - _net_at > 60:
        try:
            socket.create_connection(("api.deepseek.com", 443), timeout=2).close()
            _net_ok = True
        except Exception:
            _net_ok = False
        _net_at = time.time()
    return _net_ok


def llm_ready(cfg: dict) -> bool:
    """LLM 意图引擎是否配置可用。"""
    llm = cfg.get("deepseek") or {}
    provider = (llm.get("provider") or "deepseek").lower()
    if provider == "ollama":
        return bool(llm.get("model"))
    if provider == "deepseek":
        return bool((llm.get("api_key") or "").strip())
    return False
