"""本机用户库（JSON + scrypt 密码哈希）。"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import threading
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .paths import ensure_dir, users_path

_LOG = logging.getLogger(__name__)
_TZ = ZoneInfo("Asia/Shanghai")
_LOCK = threading.Lock()

# 仅首次种子写入；已有 users.json 则跳过（含已改密）
# 默认口令仅供本机回环演示；启动会打警告，请立即改密（POST /api/auth/change-password）
_SEED = (
    {"username": "admin", "password": "admin123", "role": "admin", "display_name": "管理员"},
    {"username": "hebo", "password": "hebo123", "role": "user", "display_name": "Hebo"},
)

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


def _now_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    pad = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def check_password(password: str, encoded: str) -> bool:
    try:
        algo, n_s, r_s, p_s, salt_b64, hash_b64 = encoded.split("$", 5)
        if algo != "scrypt":
            return False
        salt = _b64d(salt_b64)
        expect = _b64d(hash_b64)
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(expect),
        )
        return secrets.compare_digest(dk, expect)
    except (ValueError, TypeError, OSError):
        return False


def _user_id_for(username: str) -> str:
    return "u_" + "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in username.strip().lower())


def _read_raw() -> dict[str, Any]:
    path = users_path()
    if not path.is_file():
        return {"version": 1, "users": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": 1, "users": []}
        users = data.get("users")
        if not isinstance(users, list):
            data["users"] = []
        return data
    except (OSError, json.JSONDecodeError):
        _LOG.warning("auth users.json 读取失败，将重建种子", exc_info=True)
        return {"version": 1, "users": []}


def _write_raw(data: dict[str, Any]) -> None:
    ensure_dir()
    path = users_path()
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def ensure_seed_users() -> None:
    """首次启动写入演示账号；已有文件则不改。"""
    with _LOCK:
        path = users_path()
        if path.is_file():
            return
        users: list[dict[str, Any]] = []
        for row in _SEED:
            users.append(
                {
                    "id": _user_id_for(row["username"]),
                    "username": row["username"],
                    "display_name": row["display_name"],
                    "role": row["role"],
                    "password_hash": hash_password(row["password"]),
                    "created_at": _now_iso(),
                    "disabled": False,
                    "must_change_password": False,
                }
            )
        _write_raw({"version": 1, "users": users})
        _LOG.warning(
            "auth: 已写入种子账号 %s（默认口令 admin123/hebo123，请立即 POST /api/auth/change-password 改密；引擎请仅绑回环）",
            ", ".join(u["username"] for u in users),
        )


def find_user(username: str) -> dict[str, Any] | None:
    name = (username or "").strip().lower()
    if not name:
        return None
    with _LOCK:
        for u in _read_raw().get("users") or []:
            if not isinstance(u, dict):
                continue
            if str(u.get("username") or "").strip().lower() == name:
                return u
    return None


def find_user_by_id(user_id: str) -> dict[str, Any] | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    with _LOCK:
        for u in _read_raw().get("users") or []:
            if not isinstance(u, dict):
                continue
            if str(u.get("id") or "").strip() == uid:
                return u
    return None


def list_public_users(*, include_disabled: bool = False) -> list[dict[str, Any]]:
    """全部本机账号公开信息（含 admin），供企业用量按员工补齐零用量行。"""
    out: list[dict[str, Any]] = []
    with _LOCK:
        for u in _read_raw().get("users") or []:
            if not isinstance(u, dict):
                continue
            if not include_disabled and u.get("disabled"):
                continue
            pub = public_user(u)
            if pub and pub.get("id"):
                out.append(pub)
    out.sort(key=lambda x: str(x.get("username") or ""))
    return out


def verify_password(username: str, password: str) -> dict[str, Any] | None:
    u = find_user(username)
    if not u or u.get("disabled"):
        return None
    if not check_password(password or "", str(u.get("password_hash") or "")):
        return None
    return u


def change_password(username: str, old_password: str, new_password: str) -> dict[str, Any] | None:
    """校验旧密码后改密，并清除 must_change_password。新密码至少 8 位。"""
    name = (username or "").strip()
    new_pw = new_password or ""
    if len(new_pw) < 8:
        return None
    u = verify_password(name, old_password or "")
    if not u:
        return None
    uid = str(u.get("id") or "")
    with _LOCK:
        data = _read_raw()
        users = data.get("users") or []
        for i, row in enumerate(users):
            if not isinstance(row, dict):
                continue
            if str(row.get("id") or "") != uid:
                continue
            row = dict(row)
            row["password_hash"] = hash_password(new_pw)
            row["must_change_password"] = False
            row["password_changed_at"] = _now_iso()
            users[i] = row
            data["users"] = users
            _write_raw(data)
            return row
    return None


def clear_must_change_password_for_tests() -> None:
    """测试专用：种子账号跳过强制改密。"""
    with _LOCK:
        data = _read_raw()
        users = data.get("users") or []
        changed = False
        for i, row in enumerate(users):
            if not isinstance(row, dict):
                continue
            if row.get("must_change_password"):
                row = dict(row)
                row["must_change_password"] = False
                users[i] = row
                changed = True
        if changed:
            data["users"] = users
            _write_raw(data)


def set_user_disabled(user_id: str, disabled: bool = True) -> bool:
    """禁用/启用账号（管理员运维或测试用）。"""
    uid = (user_id or "").strip()
    if not uid:
        return False
    with _LOCK:
        data = _read_raw()
        users = data.get("users") or []
        for i, row in enumerate(users):
            if not isinstance(row, dict):
                continue
            if str(row.get("id") or "") != uid:
                continue
            row = dict(row)
            row["disabled"] = bool(disabled)
            users[i] = row
            data["users"] = users
            _write_raw(data)
            return True
    return False


def user_is_active(row: dict[str, Any] | None) -> bool:
    """存在且未禁用。"""
    if not row or not isinstance(row, dict):
        return False
    if row.get("disabled"):
        return False
    if not str(row.get("id") or "").strip():
        return False
    return True


def public_user(u: dict[str, Any] | None) -> dict[str, Any] | None:
    if not u:
        return None
    return {
        "id": str(u.get("id") or ""),
        "username": str(u.get("username") or ""),
        "display_name": str(u.get("display_name") or u.get("username") or ""),
        "role": str(u.get("role") or "user"),
        "must_change_password": bool(u.get("must_change_password")),
    }
