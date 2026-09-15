"""保留策略清理。"""
from __future__ import annotations

import logging
import time
from typing import Any

from . import catalog
from .config import get_space_config

_LOG = logging.getLogger(__name__)


def purge_expired(
    *,
    user_id: str = "",
    dry_run: bool = False,
    retention_days: int | None = None,
) -> dict[str, Any]:
    cfg = get_space_config()
    days = cfg.get("retention_days") if retention_days is None else retention_days
    try:
        days_i = int(days)
    except (TypeError, ValueError):
        days_i = 90
    if days_i <= 0:
        return {
            "ok": True,
            "purged_sessions": 0,
            "dry_run": bool(dry_run),
            "detail": "保留天数≤0，不自动清理",
            "retention_days": days_i,
        }
    cutoff = int(time.time()) - days_i * 86400
    try:
        ids = catalog.list_expired_session_ids(older_than_ts=cutoff, user_id=user_id)
    except Exception:
        _LOG.warning("space list expired failed", exc_info=True)
        return {"ok": False, "detail": "列举过期会话失败", "purged_sessions": 0}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "purged_sessions": len(ids),
            "session_ids": ids[:100],
            "retention_days": days_i,
        }
    n = 0
    for sid in ids:
        try:
            if catalog.delete_session(sid, user_id=user_id, admin=not bool(user_id), cascade_artifacts=True):
                n += 1
        except Exception:
            _LOG.warning("space purge session failed id=%s", sid, exc_info=True)
    return {
        "ok": True,
        "dry_run": False,
        "purged_sessions": n,
        "retention_days": days_i,
    }
