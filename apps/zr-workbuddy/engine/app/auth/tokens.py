"""本机 HS256 会话 JWT（stdlib，无第三方依赖）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from .paths import ensure_dir, jwt_secret_path

# 7 天；本机信任模型，过期后需重新登录
TOKEN_TTL_SEC = 7 * 24 * 3600


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    pad = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def _load_or_create_secret() -> bytes:
    ensure_dir()
    path = jwt_secret_path()
    if path.is_file():
        raw = path.read_bytes().strip()
        if len(raw) >= 32:
            return raw
    secret = secrets.token_bytes(48)
    path.write_bytes(secret)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


def issue_token(*, user_id: str, username: str, role: str, ttl_sec: int = TOKEN_TTL_SEC) -> tuple[str, int]:
    now = int(time.time())
    exp = now + max(60, int(ttl_sec))
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": exp,
    }
    h = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    msg = f"{h}.{p}".encode("ascii")
    sig = hmac.new(_load_or_create_secret(), msg, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}", exp


def verify_token(token: str) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not raw or raw.count(".") != 2:
        return None
    h, p, s = raw.split(".", 2)
    msg = f"{h}.{p}".encode("ascii")
    try:
        sig = _b64url_decode(s)
    except (ValueError, TypeError):
        return None
    expect = hmac.new(_load_or_create_secret(), msg, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64url_decode(p).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        exp = int(payload.get("exp") or 0)
    except (TypeError, ValueError):
        return None
    if exp < int(time.time()):
        return None
    sub = str(payload.get("sub") or "").strip()
    if not sub:
        return None
    return {
        "id": sub,
        "username": str(payload.get("username") or ""),
        "role": str(payload.get("role") or "user"),
        "exp": exp,
    }
