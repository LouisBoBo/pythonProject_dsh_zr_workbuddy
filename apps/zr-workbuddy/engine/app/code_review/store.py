"""审码报告持久化。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _data_dir(base: Path | None = None) -> Path:
    if base is None:
        base = Path(__file__).resolve().parents[2] / "data"
    d = base / "code_review" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_report_id() -> str:
    return f"cr-{uuid.uuid4().hex[:16]}"


def save_report(data_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    rid = str(report.get("id") or new_report_id())
    report = {**report, "id": rid}
    if not report.get("created_at"):
        report["created_at"] = datetime.now(timezone.utc).isoformat()
    path = _data_dir(data_dir) / f"{rid}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def load_report(data_dir: Path, report_id: str) -> dict[str, Any] | None:
    safe = "".join(c for c in (report_id or "") if c.isalnum() or c in "-_")
    if not safe or safe != report_id:
        return None
    path = _data_dir(data_dir) / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
