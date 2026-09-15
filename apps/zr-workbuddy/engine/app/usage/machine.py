"""本机稳定 machine_id（用量上报去重辅助）。"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

_ENGINE_ROOT = Path(__file__).resolve().parents[2]


def machine_id_path() -> Path:
    try:
        from .store import _dir

        return Path(_dir()) / "machine_id"
    except Exception:
        return _ENGINE_ROOT / "data" / "usage" / "machine_id"


def get_machine_id() -> str:
    path = machine_id_path()
    try:
        if path.is_file():
            raw = path.read_text(encoding="utf-8").strip()
            if raw.startswith("mch_") and len(raw) >= 12:
                return raw[:80]
    except OSError:
        pass
    mid = "mch_" + secrets.token_hex(12)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(mid + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        pass
    return mid
