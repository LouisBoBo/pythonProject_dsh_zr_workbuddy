"""auth 数据目录与路径。"""
from __future__ import annotations

import os
from pathlib import Path

_ENGINE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DIR = _ENGINE_ROOT / "data" / "auth"

_data_dir_override: str | None = None


def set_data_dir(path: str | None) -> None:
    global _data_dir_override
    _data_dir_override = path


def data_dir() -> Path:
    if _data_dir_override:
        return Path(_data_dir_override)
    return _DEFAULT_DIR


def users_path() -> Path:
    return data_dir() / "users.json"


def jwt_secret_path() -> Path:
    return data_dir() / "jwt_secret"


def active_path() -> Path:
    return data_dir() / "active.json"


def ensure_dir() -> Path:
    d = data_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d
