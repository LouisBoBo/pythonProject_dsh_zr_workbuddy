"""从本机外部草稿目录同步进「我的空间」（不改 DSH 插件）。

当前：`~/.zhongruan/pcb-8d-drafts/*.md`（@zhongruan/dsh-pcb-8d 落盘）。
全部 fail-soft；路径必须落在用户 home 下。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from . import catalog
from .config import get_space_config
from .redact import redact_text

_LOG = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"^#\s+(.+)$", re.M)
_SYNC_LAST_AT: dict[str, float] = {}
_SYNC_THROTTLE_SEC = 20.0


def pcb_8d_drafts_dir() -> Path | None:
    """返回可扫描的 8D 草稿目录；非法路径返回 None。"""
    cfg = get_space_config()
    if cfg.get("sync_pcb_8d") is False:
        return None
    raw = str(cfg.get("pcb_8d_drafts_dir") or "").strip()
    try:
        home = Path.home().resolve()
        if raw:
            base = Path(raw).expanduser().resolve()
        else:
            base = (home / ".zhongruan" / "pcb-8d-drafts").resolve()
        try:
            base.relative_to(home)
        except ValueError:
            _LOG.warning("space pcb_8d drafts dir outside home, skip: %s", base)
            return None
        if raw and ".." in Path(raw).expanduser().parts:
            return None
        return base
    except OSError:
        return None


def _title_from_md(text: str, stem: str) -> str:
    m = _TITLE_RE.search(text or "")
    if m:
        t = m.group(1).strip()
        t = re.sub(r"[（(][^）)]{3,80}[）)]\s*$", "", t).strip()
        return (t or f"8D 报告 {stem}")[:200]
    return f"8D 报告 {stem}"[:200]


def _safe_artifact_id(stem: str) -> str | None:
    s = str(stem or "").strip()
    if not s or "/" in s or "\\" in s or ".." in s:
        return None
    # 插件文件名形如 8D-20260915-1357-d106；也允许 DEMO 等
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,120}$", s):
        return None
    return s


def ingest_pcb_8d_markdown(
    *,
    path: Path,
    user_id: str,
    max_chars: int,
) -> bool:
    """将一份 .md 拷入空间；成功 True。时间用文件 mtime（不是扫目录时刻）。"""
    aid = _safe_artifact_id(path.stem)
    if not aid:
        return False
    try:
        st = path.stat()
        text = path.read_text(encoding="utf-8")
        mtime = int(st.st_mtime)
    except OSError:
        return False
    if not text.strip():
        return False
    title = _title_from_md(text, aid)
    sess_title = f"PCB 8D · {aid}"
    body, truncated = redact_text(text, max_chars=max(max_chars, 200_000))
    uid = str(user_id or "").strip() or "anonymous"
    sid = f"pcb8d:{aid}"
    summary_body, _ = redact_text(
        f"【PCB 8D】{sess_title}\n报告：{title}\n来源：pcb-8d-drafts/{path.name}\n",
        max_chars=max_chars,
    )
    catalog.upsert_session(
        session_id=sid,
        user_id=uid,
        source="pcb_8d",
        title=sess_title,
        body_text=summary_body,
        body_kind="summary",
        body_truncated=truncated or len(body) > 1200,
        at=mtime,
    )
    relpath, nbytes = catalog.write_report_file(
        user_id=uid,
        artifact_id=aid,
        body=body,
        ext="md",
    )
    catalog.upsert_artifact(
        artifact_id=aid,
        session_id=sid,
        user_id=uid,
        kind="pcb_8d_report",
        title=title,
        relpath=relpath,
        summary=f"PCB 8D · {path.name}",
        bytes_n=nbytes,
        call_id="",
        at=mtime,
    )
    return True


def sync_pcb_8d_drafts(user_id: str = "") -> dict[str, Any]:
    """扫描草稿目录，把 .md 同步进当前用户空间。失败不抛。"""
    out: dict[str, Any] = {"ok": True, "scanned": 0, "ingested": 0, "skipped": 0}
    try:
        uid = str(user_id or "").strip()
        if not uid:
            return {**out, "ok": False, "detail": "no user"}
        root = pcb_8d_drafts_dir()
        if root is None or not root.is_dir():
            return out
        cfg = get_space_config()
        max_chars = int(cfg.get("max_session_body_chars") or 65536)
        for path in sorted(root.glob("*.md")):
            out["scanned"] += 1
            try:
                existing = catalog.get_artifact(path.stem)
                if existing:
                    owner = str(existing.get("user_id") or "").strip()
                    if owner and owner != uid:
                        out["skipped"] += 1
                        continue
                if ingest_pcb_8d_markdown(path=path, user_id=uid, max_chars=max_chars):
                    out["ingested"] += 1
                else:
                    out["skipped"] += 1
            except Exception:
                out["skipped"] += 1
                _LOG.debug("space sync one pcb_8d failed path=%s", path, exc_info=True)
    except Exception:
        _LOG.warning("space sync_pcb_8d_drafts failed", exc_info=True)
        return {"ok": False, "scanned": out["scanned"], "ingested": out["ingested"], "skipped": out["skipped"]}
    return out


def sync_external_into_space(user_id: str = "") -> dict[str, Any]:
    """打开「我的空间」前调用的聚合同步（可扩展其它外部产物）。"""
    import time as _time

    out: dict[str, Any] = {"ok": True}
    uid = str(user_id or "").strip()
    # 短节流：避免翻页/连点刷新重复扫盘
    now = _time.time()
    last = float(_SYNC_LAST_AT.get(uid) or 0) if uid else 0.0
    if uid and now - last < _SYNC_THROTTLE_SEC:
        out["throttled"] = True
        return out
    if uid:
        _SYNC_LAST_AT[uid] = now

    try:
        out["pcb_8d"] = sync_pcb_8d_drafts(user_id=user_id)
    except Exception:
        _LOG.warning("space sync_external_into_space pcb_8d failed", exc_info=True)
        out["pcb_8d"] = {"ok": False}
    try:
        from .chat_docs import sync_chat_docs_from_dsh

        out["chat_docs"] = sync_chat_docs_from_dsh(user_id=user_id)
    except Exception:
        _LOG.warning("space sync_external_into_space chat_docs failed", exc_info=True)
        out["chat_docs"] = {"ok": False}
    try:
        from .hooks import backfill_code_dev_files

        out["code_dev"] = backfill_code_dev_files(user_id=user_id, limit=40)
    except Exception:
        _LOG.warning("space sync_external_into_space code_dev failed", exc_info=True)
        out["code_dev"] = {"ok": False}
    return out
