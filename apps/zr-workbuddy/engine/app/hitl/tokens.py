"""HITL nonce / path_ticket 内存存储（进程内；重启失效可接受）。"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any

_PAYLOAD_HASH_RE = re.compile(r"^[0-9a-f]{32,64}$")

_LOCK = threading.Lock()
_STORE: dict[str, dict[str, Any]] = {}

DEFAULT_TTL_SEC = 300
PATH_TTL_SEC = 600

ACTION_DEV = "code-dev.confirm"
ACTION_COMMIT = "code-commit.confirm"
ACTION_DEPLOY = "code-deploy.confirm"
ACTION_PATH = "code-review.path"

_KNOWN_ACTIONS = frozenset({ACTION_DEV, ACTION_COMMIT, ACTION_DEPLOY, ACTION_PATH})

# 公开 HTTP /api/hitl/issue 仅允许确认类；path_ticket 只经 list/check 内 attach
HTTP_ISSUE_ACTIONS = frozenset({ACTION_DEV, ACTION_COMMIT, ACTION_DEPLOY})


def reset_store_for_tests() -> None:
    with _LOCK:
        _STORE.clear()


def _purge(now: float) -> None:
    dead = [k for k, v in _STORE.items() if float(v.get("exp") or 0) < now]
    for k in dead:
        _STORE.pop(k, None)


def normalize_payload_hash(raw: str) -> str:
    """需求摘要等绑定物的稳定短哈希（空串表示未绑定）。"""
    s = " ".join(str(raw or "").split())
    if not s:
        return ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:32]


def normalize_bind_path(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        return ""
    try:
        return str(Path(raw).expanduser().resolve())
    except OSError:
        return raw


def issue(
    *,
    action: str,
    workspace: str = "",
    job_id: str = "",
    path: str = "",
    payload_hash: str = "",
    ttl_sec: int | None = None,
) -> dict[str, Any]:
    """签发一次性票据。返回 {ok, nonce, action, exp, …}。"""
    act = (action or "").strip()
    if act not in _KNOWN_ACTIONS:
        return {"ok": False, "detail": f"未知 HITL action：{act or '(空)'}"}

    jid = (job_id or "").strip()
    ws = normalize_bind_path(workspace) if workspace else ""
    p = normalize_bind_path(path) if path else ""
    ph = (payload_hash or "").strip().lower()
    if ph and not _PAYLOAD_HASH_RE.fullmatch(ph):
        return {"ok": False, "detail": "payload_hash 格式无效（须为 sha256 十六进制截断）"}

    if act in {ACTION_DEV} and not ws:
        return {"ok": False, "detail": "code-dev.confirm 须绑定 workspace"}
    if act in {ACTION_DEV} and not ph:
        return {"ok": False, "detail": "code-dev.confirm 须绑定需求摘要 hash"}
    if act in {ACTION_COMMIT, ACTION_DEPLOY} and not jid:
        return {"ok": False, "detail": f"{act} 须绑定 job_id"}
    if act == ACTION_PATH and not p:
        return {"ok": False, "detail": "code-review.path 须绑定 path"}

    ttl = int(ttl_sec if ttl_sec is not None else (PATH_TTL_SEC if act == ACTION_PATH else DEFAULT_TTL_SEC))
    ttl = max(30, min(ttl, 1800))
    now = time.time()
    nonce = "htl_" + secrets.token_urlsafe(24)
    rec = {
        "action": act,
        "workspace": ws,
        "job_id": jid,
        "path": p,
        "payload_hash": ph,
        "exp": now + ttl,
        "jti": secrets.token_hex(8),
    }
    with _LOCK:
        _purge(now)
        _STORE[nonce] = rec
    return {
        "ok": True,
        "nonce": nonce,
        "action": act,
        "exp": int(rec["exp"]),
        "ttl_sec": ttl,
        "workspace": ws or None,
        "job_id": jid or None,
        "path": p or None,
    }


def issue_path_ticket(path: str, *, ttl_sec: int | None = None) -> dict[str, Any]:
    return issue(action=ACTION_PATH, path=path, ttl_sec=ttl_sec)


def consume(
    *,
    nonce: str,
    action: str,
    workspace: str = "",
    job_id: str = "",
    path: str = "",
    payload_hash: str = "",
) -> dict[str, Any]:
    """校验并作废票据。成功 {ok: True}；失败带 detail。"""
    token = (nonce or "").strip()
    act = (action or "").strip()
    if not token:
        return {
            "ok": False,
            "detail": "缺少 HITL nonce：请在确认卡点击确认（勿仅用 Agent confirmed=true）",
            "code": "hitl_nonce_missing",
        }
    if act not in _KNOWN_ACTIONS:
        return {"ok": False, "detail": f"未知 HITL action：{act}", "code": "hitl_bad_action"}

    now = time.time()
    with _LOCK:
        _purge(now)
        rec = _STORE.pop(token, None)

    if not rec:
        return {
            "ok": False,
            "detail": "HITL nonce 无效或已使用/过期，请重新在确认卡操作",
            "code": "hitl_nonce_invalid",
        }
    if rec.get("action") != act:
        return {
            "ok": False,
            "detail": f"HITL nonce 动作不匹配（期望 {act}）",
            "code": "hitl_action_mismatch",
        }
    if float(rec.get("exp") or 0) < now:
        return {
            "ok": False,
            "detail": "HITL nonce 已过期，请重新确认",
            "code": "hitl_nonce_expired",
        }

    if act == ACTION_DEV:
        want = normalize_bind_path(workspace)
        got = str(rec.get("workspace") or "")
        if not want or want != got:
            return {
                "ok": False,
                "detail": "HITL nonce 与 workspace 不匹配",
                "code": "hitl_bind_mismatch",
            }
        want_h = (payload_hash or "").strip().lower()
        got_h = str(rec.get("payload_hash") or "").strip().lower()
        # 旧票据无 hash 时兼容；签发时带了 hash 则确认必须一致
        if got_h and want_h != got_h:
            return {
                "ok": False,
                "detail": "HITL nonce 与需求摘要不匹配（请重新点确认卡）",
                "code": "hitl_payload_mismatch",
            }
    elif act in {ACTION_COMMIT, ACTION_DEPLOY}:
        want = (job_id or "").strip()
        got = str(rec.get("job_id") or "")
        if not want or want != got:
            return {
                "ok": False,
                "detail": "HITL nonce 与 job_id 不匹配",
                "code": "hitl_bind_mismatch",
            }
    elif act == ACTION_PATH:
        want = normalize_bind_path(path)
        got = str(rec.get("path") or "")
        if not want or want != got:
            return {
                "ok": False,
                "detail": "path_ticket 与路径不匹配",
                "code": "hitl_bind_mismatch",
            }

    return {"ok": True, "jti": rec.get("jti"), "action": act}


def require_confirm_nonce(
    *,
    nonce: str,
    action: str,
    workspace: str = "",
    job_id: str = "",
    payload_hash: str = "",
) -> dict[str, Any]:
    return consume(
        nonce=nonce,
        action=action,
        workspace=workspace,
        job_id=job_id,
        payload_hash=payload_hash,
    )


def attach_path_ticket(payload: dict[str, Any], path: str) -> dict[str, Any]:
    """在校验成功的路径响应上附带 path_ticket（不改变 ok=false）。"""
    if not payload.get("ok"):
        return payload
    issued = issue_path_ticket(path)
    if not issued.get("ok"):
        return payload
    out = dict(payload)
    out["path_ticket"] = issued["nonce"]
    out["path_ticket_exp"] = issued.get("exp")
    return out


def gate_review_path(
    *,
    local_path: str,
    path_ticket: str = "",
    allow_agent_absolute_path: bool = False,
) -> dict[str, Any]:
    """审码开跑前门禁：默认须 path_ticket。"""
    path = (local_path or "").strip()
    if not path:
        return {"ok": False, "detail": "local_path 不能为空", "code": "path_empty"}
    ticket = (path_ticket or "").strip()
    if ticket:
        return consume(nonce=ticket, action=ACTION_PATH, path=path)
    if allow_agent_absolute_path:
        return {"ok": True, "detail": "allow_agent_absolute_path"}
    return {
        "ok": False,
        "detail": "须经选目录/列文件签发的 path_ticket；禁止裸绝对路径直跑（企业硬门禁）",
        "code": "path_ticket_missing",
        "reply": "请在工具卡中选择目录并列出文件后再开始审核。",
    }
