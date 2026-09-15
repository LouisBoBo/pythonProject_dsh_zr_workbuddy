"""本机当前登录用户（文件），供非 HTTP 路径（LLM 记账）读取 user_id。"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from .paths import active_path, ensure_dir

_LOG = logging.getLogger(__name__)
_LOCK = threading.Lock()


def set_active(user: dict[str, Any], *, exp: int) -> None:
    ensure_dir()
    body = {
        "id": str(user.get("id") or ""),
        "username": str(user.get("username") or ""),
        "display_name": str(user.get("display_name") or user.get("username") or ""),
        "role": str(user.get("role") or "user"),
        "exp": int(exp),
        "updated_at": int(time.time()),
    }
    path = active_path()
    tmp = path.with_suffix(".tmp")
    with _LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def clear_active() -> None:
    path = active_path()
    with _LOCK:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            _LOG.warning("auth clear active failed", exc_info=True)


def get_active_user() -> dict[str, Any] | None:
    path = active_path()
    with _LOCK:
        if not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    if not isinstance(data, dict):
        return None
    try:
        exp = int(data.get("exp") or 0)
    except (TypeError, ValueError):
        return None
    if exp < int(time.time()):
        return None
    uid = str(data.get("id") or "").strip()
    if not uid:
        return None
    return {
        "id": uid,
        "username": str(data.get("username") or ""),
        "display_name": str(data.get("display_name") or data.get("username") or ""),
        "role": str(data.get("role") or "user"),
        "exp": exp,
    }
