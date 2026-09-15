"""绑定 / 打开 DSH 会话：只认入库时写死的 session-uuid，不做内容启发式反查。

资料库 catalog id（pcb8d:… / review:cr-…）与 DSH session-uuid 不是同一套。
点「打开会话」必须已有 dsh_path 或档案 id 本身就是 session-…；猜不准的扫描一律不做。
"""
from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger(__name__)


def looks_like_dsh_session_id(raw: str) -> str:
    s = str(raw or "").strip()
    if s.startswith("session-") and len(s) > 12:
        return s
    if len(s) == 36 and s.count("-") == 4:
        return "session-" + s
    return ""


def bound_dsh_session_id(*, catalog_id: str = "", dsh_path: str = "") -> str:
    """从档案字段取出已绑定的 DSH session id；没有则空串。"""
    return looks_like_dsh_session_id(dsh_path) or looks_like_dsh_session_id(catalog_id)


def locate_dsh_session(
    *,
    catalog_id: str = "",
    needle: str = "",
    catalog_source: str = "",
    cached_dsh_id: str = "",
) -> dict[str, Any]:
    """仅返回已绑定 id。needle / 扫描参数保留兼容，但忽略（禁止猜）。"""
    _ = needle, catalog_source  # 故意不用：反查会误命中相似会话
    out: dict[str, Any] = {
        "ok": True,
        "dsh_session_id": "",
        "dsh_title": "",
        "dsh_workspace": "",
        "match_score": 0,
        "detail": "",
    }
    try:
        sid = bound_dsh_session_id(catalog_id=catalog_id, dsh_path=cached_dsh_id)
        if sid:
            out["dsh_session_id"] = sid
            out["match_score"] = 100
            out["detail"] = "bound"
            return out
        out["detail"] = "no-binding"
    except Exception:
        _LOG.debug("locate_dsh_session failed", exc_info=True)
        out["detail"] = "error"
    return out
