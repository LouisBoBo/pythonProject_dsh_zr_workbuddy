"""我的空间配置（失败时回退默认，不抛）。"""
from __future__ import annotations

from typing import Any


_DEFAULTS = {
    "retention_days": 90,
    "max_session_body_chars": 65536,
    "auto_purge_enabled": True,
    "sync_pcb_8d": True,
    "pcb_8d_drafts_dir": "",  # 空 = ~/.zhongruan/pcb-8d-drafts
    "sync_chat_docs": True,
    "ingest_code_files": True,  # 写码成功后把已同步源码副本进资料库
    "code_file_max_count": 20,
    "code_file_max_bytes": 262144,  # 单文件上限 256KB
}


def get_space_config() -> dict[str, Any]:
    out = dict(_DEFAULTS)
    try:
        from ..config_store import load_config

        raw = (load_config() or {}).get("space") or {}
        if isinstance(raw, dict):
            if "retention_days" in raw:
                try:
                    out["retention_days"] = max(0, int(raw["retention_days"]))
                except (TypeError, ValueError):
                    pass
            if "max_session_body_chars" in raw:
                try:
                    out["max_session_body_chars"] = max(1024, int(raw["max_session_body_chars"]))
                except (TypeError, ValueError):
                    pass
            if "auto_purge_enabled" in raw:
                out["auto_purge_enabled"] = bool(raw["auto_purge_enabled"])
            if "sync_pcb_8d" in raw:
                out["sync_pcb_8d"] = bool(raw["sync_pcb_8d"])
            if "pcb_8d_drafts_dir" in raw and raw["pcb_8d_drafts_dir"] is not None:
                out["pcb_8d_drafts_dir"] = str(raw["pcb_8d_drafts_dir"]).strip()
            if "sync_chat_docs" in raw:
                out["sync_chat_docs"] = bool(raw["sync_chat_docs"])
            if "ingest_code_files" in raw:
                out["ingest_code_files"] = bool(raw["ingest_code_files"])
            if "code_file_max_count" in raw:
                try:
                    out["code_file_max_count"] = max(1, min(50, int(raw["code_file_max_count"])))
                except (TypeError, ValueError):
                    pass
            if "code_file_max_bytes" in raw:
                try:
                    out["code_file_max_bytes"] = max(4096, min(2_000_000, int(raw["code_file_max_bytes"])))
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return out
