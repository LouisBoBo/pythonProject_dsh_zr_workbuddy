"""企业级安全审计（P1）：旁路落盘，失败永不阻断业务。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_MAX_LINE = 4000


def _data_root() -> Path:
    try:
        from .code_dev.service import default_data_dir

        return Path(default_data_dir())
    except Exception:
        return Path(__file__).resolve().parents[1] / "data"


def audit_path() -> Path:
    d = _data_root() / "security"
    d.mkdir(parents=True, exist_ok=True)
    return d / "audit.jsonl"


def append_audit(event: str, **fields: Any) -> None:
    """写入一条审计事件。任何异常静默吞掉。"""
    try:
        row: dict[str, Any] = {
            "ts": int(time.time()),
            "event": str(event or "").strip()[:80] or "unknown",
        }
        for k, v in fields.items():
            if v is None:
                continue
            key = str(k)[:64]
            if isinstance(v, (bool, int, float)):
                row[key] = v
            else:
                s = str(v)
                if len(s) > 500:
                    s = s[:500] + "…"
                row[key] = s
        line = json.dumps(row, ensure_ascii=False)
        if len(line) > _MAX_LINE:
            line = line[: _MAX_LINE - 1] + "…"
        path = audit_path()
        with _lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        return
