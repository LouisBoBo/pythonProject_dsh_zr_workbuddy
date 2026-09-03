"""提交任务持久化：engine/data/code_commit/jobs/。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# awaiting_commit | blocked | done | skipped | committing
JOB_STATUSES = frozenset({"awaiting_commit", "blocked", "done", "skipped", "committing"})


def _jobs_dir(base: Path | None = None) -> Path:
    if base is None:
        base = Path(__file__).resolve().parents[2] / "data"
    d = base / "code_commit" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_job_id() -> str:
    return f"cc-{uuid.uuid4().hex[:16]}"


def save_job(data_dir: Path, job: dict[str, Any]) -> dict[str, Any]:
    jid = str(job.get("id") or new_job_id())
    job = {**job, "id": jid}
    if not job.get("created_at"):
        job["created_at"] = datetime.now(timezone.utc).isoformat()
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    status = str(job.get("status") or "awaiting_commit")
    if status not in JOB_STATUSES:
        status = "awaiting_commit"
        job["status"] = status
    path = _jobs_dir(data_dir) / f"{jid}.json"
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def load_job(data_dir: Path, job_id: str) -> dict[str, Any] | None:
    safe = "".join(c for c in (job_id or "") if c.isalnum() or c in "-_")
    if not safe or safe != job_id:
        return None
    path = _jobs_dir(data_dir) / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def update_job(data_dir: Path, job_id: str, **fields: Any) -> dict[str, Any] | None:
    row = load_job(data_dir, job_id)
    if not row:
        return None
    row.update(fields)
    return save_job(data_dir, row)


def supersede_awaiting_for_workspace(data_dir: Path, workspace: str, *, keep_id: str = "") -> int:
    """同仓库新开闸时，作废旧的 awaiting_commit，避免过期确认卡仍可提交。"""
    ws = str(workspace or "").strip()
    if not ws:
        return 0
    n = 0
    for path in _jobs_dir(data_dir).glob("cc-*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict):
            continue
        if row.get("id") == keep_id:
            continue
        if row.get("status") != "awaiting_commit":
            continue
        if str(row.get("workspace") or "").strip() != ws:
            continue
        row["status"] = "skipped"
        row["note"] = "superseded_by_new_gate"
        save_job(data_dir, row)
        n += 1
    return n


def claim_job_for_commit(data_dir: Path, job_id: str) -> dict[str, Any] | None:
    """CAS：仅 awaiting_commit → committing，防并发双确认。"""
    row = load_job(data_dir, job_id)
    if not row or row.get("status") != "awaiting_commit":
        return None
    row["status"] = "committing"
    return save_job(data_dir, row)


def list_jobs(data_dir: Path, *, limit: int = 40) -> list[dict[str, Any]]:
    """按更新时间倒序列出提交任务（最多 limit 条）。"""
    rows: list[tuple[float, dict[str, Any]]] = []
    for path in _jobs_dir(data_dir).glob("cc-*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        rows.append((mtime, row))
    rows.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in rows[: max(1, min(int(limit or 40), 100))]]


def latest_blocked_job(
    data_dir: Path,
    *,
    workspace: str = "",
    job_id: str = "",
) -> dict[str, Any] | None:
    """取最近一次 status=blocked 的门禁任务；可按 workspace / job_id 过滤。"""
    jid = (job_id or "").strip()
    if jid:
        row = load_job(data_dir, jid)
        if row and row.get("status") == "blocked":
            return row
        return None
    ws = str(workspace or "").strip()
    try:
        ws_norm = str(Path(ws).expanduser().resolve()) if ws else ""
    except OSError:
        ws_norm = ws
    for row in list_jobs(data_dir, limit=60):
        if row.get("status") != "blocked":
            continue
        if not ws_norm:
            return row
        jws = str(row.get("workspace") or "").strip()
        try:
            jws_n = str(Path(jws).expanduser().resolve()) if jws else ""
        except OSError:
            jws_n = jws
        if jws_n == ws_norm or jws == ws:
            return row
    return None


def latest_done_workspace(data_dir: Path) -> str:
    """最近一次成功提交（status=done）的工程路径。"""
    for row in list_jobs(data_dir, limit=40):
        if row.get("status") != "done":
            continue
        ws = str(row.get("workspace") or "").strip()
        if ws:
            return ws
    return ""
