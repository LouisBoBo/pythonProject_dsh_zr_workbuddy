"""读取 engine/config/runtime.yaml —— 委托仓库唯一实现 scripts/lib/read_runtime.py。"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict

_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_ENGINE_ROOT)))
_HELPER = os.path.join(_REPO_ROOT, "scripts", "lib", "read_runtime.py")


def _fallback_runtime() -> Dict[str, Any]:
    """与 scripts/lib/read_runtime.py 的环境变量约定保持一致。"""
    host = os.environ.get("APP_ENGINE_HOST") or "127.0.0.1"
    port_raw = os.environ.get("APP_ENGINE_PORT") or "8000"
    python = os.environ.get("APP_ENGINE_PYTHON") or "python3"
    try:
        port = int(port_raw)
    except Exception:
        port = 8000
    return {"host": str(host), "port": port, "python": str(python)}


def read_runtime() -> Dict[str, Any]:
    path = os.path.join(_ENGINE_ROOT, "config", "runtime.yaml")
    if os.path.isfile(_HELPER):
        spec = importlib.util.spec_from_file_location("dsh_read_runtime", _HELPER)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.read_runtime(path)
    return _fallback_runtime()
