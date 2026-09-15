"""本机用量增量上报到内网汇总（失败不得影响聊天/写码）。"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from .machine import get_machine_id
from .store import mark_reported, pending_report_events

_LOG = logging.getLogger(__name__)
_TZ = ZoneInfo("Asia/Shanghai")
_LAST_FLUSH = 0.0
_MIN_INTERVAL_SEC = 60.0
_BATCH = 200


def _usage_cfg() -> dict[str, Any]:
    try:
        from ..config_store import load_config

        cfg = load_config().get("usage") or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _url_ok(url: str) -> bool:
    try:
        u = urlparse((url or "").strip())
    except Exception:
        return False
    if u.scheme not in {"http", "https"}:
        return False
    host = (u.hostname or "").lower()
    # P0：仅允许本机回环；生产内网 URL 再放宽需另立项
    return host in {"127.0.0.1", "localhost", "::1"}


def flush_report(*, force: bool = False) -> dict[str, Any]:
    """上报待报流水。返回摘要；永不抛到调用方。"""
    global _LAST_FLUSH
    out: dict[str, Any] = {"ok": True, "skipped": True, "sent": 0, "accepted": 0, "duplicate": 0}
    try:
        now = time.monotonic()
        if not force and (now - _LAST_FLUSH) < _MIN_INTERVAL_SEC:
            out["detail"] = "throttled"
            return out
        cfg = _usage_cfg()
        if not cfg.get("report_enabled"):
            out["detail"] = "report_disabled"
            return out
        url = str(cfg.get("report_url") or "").strip().rstrip("/")
        if not url:
            out["detail"] = "no_report_url"
            return out
        if not _url_ok(url):
            out["ok"] = False
            out["detail"] = "report_url 仅允许本机回环（127.0.0.1/localhost）"
            return out
        token = str(cfg.get("report_token") or "").strip()
        pending = pending_report_events(limit=_BATCH)
        if not pending:
            _LAST_FLUSH = now
            out["skipped"] = False
            out["detail"] = "nothing_pending"
            return out
        # 按当前活跃用户拆批（方案批次带 user_id）；无 user_id 的已在 pending 排除
        by_user: dict[str, list[dict[str, Any]]] = {}
        for e in pending:
            uid = str(e.get("user_id") or "").strip()
            by_user.setdefault(uid, []).append(e)
        mid = get_machine_id()
        accepted_all: list[str] = []
        dup_all: list[str] = []
        with httpx.Client(timeout=5.0) as client:
            for uid, rows in by_user.items():
                body = {
                    "schema": 1,
                    "machine_id": mid,
                    "user_id": uid,
                    "events": [
                        {
                            "id": r.get("id"),
                            "ts": r.get("ts"),
                            "source": r.get("source"),
                            "lane": r.get("lane"),
                            "provider": r.get("provider"),
                            "model": r.get("model"),
                            "prompt_tokens": r.get("prompt_tokens"),
                            "completion_tokens": r.get("completion_tokens"),
                            "cache_read_tokens": r.get("cache_read_tokens"),
                            "cache_write_tokens": r.get("cache_write_tokens"),
                            "reasoning_tokens": r.get("reasoning_tokens"),
                            "total_tokens": r.get("total_tokens"),
                            "quality": r.get("quality"),
                            "ok": r.get("ok"),
                            "user_id": uid,
                            "machine_id": mid,
                        }
                        for r in rows
                    ],
                }
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                ingest = url + "/ingest"
                r = client.post(ingest, json=body, headers=headers)
                if r.status_code >= 400:
                    _LOG.warning("usage report HTTP %s: %s", r.status_code, (r.text or "")[:200])
                    out["ok"] = False
                    out["detail"] = f"http_{r.status_code}"
                    continue
                data = r.json() if r.content else {}
                acc = list(data.get("accepted") or [])
                dup = list(data.get("duplicate") or [])
                accepted_all.extend(str(x) for x in acc)
                dup_all.extend(str(x) for x in dup)
                done = set(accepted_all) | set(dup_all)
                if done:
                    mark_reported(
                        list(done),
                        when=datetime.now(_TZ).isoformat(timespec="seconds"),
                    )
        _LAST_FLUSH = now
        out.update(
            {
                "skipped": False,
                "sent": len(pending),
                "accepted": len(accepted_all),
                "duplicate": len(dup_all),
                "detail": "ok",
            }
        )
        return out
    except Exception:
        _LOG.warning("usage report flush failed", exc_info=True)
        return {"ok": False, "skipped": False, "detail": "exception", "sent": 0, "accepted": 0, "duplicate": 0}


def pending_count() -> int:
    try:
        return len(pending_report_events(limit=5000))
    except Exception:
        return 0
