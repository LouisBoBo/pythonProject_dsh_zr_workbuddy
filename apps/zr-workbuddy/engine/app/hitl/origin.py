"""本机变异接口 Origin/Referer 收敛（防御 CSRF；主门禁仍是 HITL nonce）。"""
from __future__ import annotations

import re
from urllib.parse import urlparse

_LOCAL_ORIGIN_RE = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", re.I)

# 浏览器确认卡签发必须带此头；无头视为脚本/Agent，拒绝签发
HITL_UI_HEADER = "x-workbuddy-hitl"
HITL_UI_HEADER_VALUE = "ui"


def mutating_path_guarded(path: str, method: str) -> bool:
    m = (method or "").upper()
    if m not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    p = path or ""
    if p.startswith("/api/hitl/"):
        return True
    if p in {
        "/api/code-dev/confirm",
        "/api/code-commit/confirm",
        "/api/code-deploy/confirm",
    }:
        return True
    if p.startswith("/api/code-dev/jobs/") and p.endswith("/cancel"):
        return True
    if p.startswith("/api/code-review/run"):
        return True
    if p.startswith("/api/config"):
        return True
    if p in {"/api/pick-folder"}:
        return True
    return False


def _origin_host_ok(value: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    if _LOCAL_ORIGIN_RE.match(raw):
        return True
    try:
        u = urlparse(raw)
        if u.scheme in {"http", "https"} and (u.hostname or "").lower() in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            return True
    except Exception:
        return False
    return False


def local_origin_ok(origin: str | None, referer: str | None) -> str | None:
    """返回 None 表示放行；否则返回拒绝原因。

    无 Origin/Referer：视为 CLI/同机脚本，放行（仍须 HITL nonce）——**签发接口另见 issue_surface_ok**。
    有 Origin 或 Referer：必须为本机回环。
    """
    o = (origin or "").strip()
    r = (referer or "").strip()
    if not o and not r:
        return None
    if o:
        return None if _origin_host_ok(o) else f"拒绝非本机 Origin：{o}"
    try:
        parsed = urlparse(r)
        ref_origin = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return "无法解析 Referer"
    return None if _origin_host_ok(ref_origin) else f"拒绝非本机 Referer：{r}"


def issue_surface_ok(
    *,
    origin: str | None,
    referer: str | None,
    ui_header: str | None,
) -> str | None:
    """签发面门禁：必须像浏览器确认卡（本机 Origin + UI 头）。

    返回 None 放行；否则拒绝原因。阻止 Agent/curl 无头自签 nonce。
    """
    hdr = (ui_header or "").strip().lower()
    if hdr != HITL_UI_HEADER_VALUE:
        return "HITL 签发仅允许确认卡 UI（缺少 X-WorkBuddy-Hitl: ui）"
    o = (origin or "").strip()
    r = (referer or "").strip()
    if not o and not r:
        return "HITL 签发须带本机 Origin 或 Referer（禁止脚本裸签）"
    return local_origin_ok(origin, referer)
