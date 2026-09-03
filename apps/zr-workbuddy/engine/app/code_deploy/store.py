"""部署 Job 持久化：engine/data/code_deploy/jobs/ + last_sha。"""
from __future__ import annotations

import fcntl
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JOB_STATUSES = frozenset(
    {"awaiting_deploy", "deploying", "done", "failed", "skipped"}
)


def _jobs_dir(base: Path | None = None) -> Path:
    if base is None:
        base = Path(__file__).resolve().parents[2] / "data"
    d = base / "code_deploy" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _meta_path(base: Path | None = None) -> Path:
    if base is None:
        base = Path(__file__).resolve().parents[2] / "data"
    d = base / "code_deploy"
    d.mkdir(parents=True, exist_ok=True)
    return d / "last_deploy.json"


def _lock_path(data_dir: Path) -> Path:
    d = Path(data_dir) / "code_deploy"
    d.mkdir(parents=True, exist_ok=True)
    return d / "jobs.lock"


def new_job_id() -> str:
    return f"cd-{uuid.uuid4().hex[:16]}"


def save_job(data_dir: Path, job: dict[str, Any]) -> dict[str, Any]:
    jid = str(job.get("id") or new_job_id())
    job = {**job, "id": jid}
    if not job.get("created_at"):
        job["created_at"] = datetime.now(timezone.utc).isoformat()
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    status = str(job.get("status") or "awaiting_deploy")
    if status not in JOB_STATUSES:
        status = "awaiting_deploy"
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


def claim_job(
    data_dir: Path,
    job_id: str,
    *,
    expect_status: str = "awaiting_deploy",
    **fields: Any,
) -> dict[str, Any] | None:
    """带 flock 的状态抢占：仅当当前 status==expect 时写入，防双确认并发。"""
    lock = _lock_path(data_dir)
    with open(lock, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            row = load_job(data_dir, job_id)
            if not row or str(row.get("status") or "") != expect_status:
                return None
            row.update(fields)
            return save_job(data_dir, row)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def get_last_deploy_record(data_dir: Path, env: str) -> dict[str, Any]:
    """读取某环境上次成功部署：sha + 脏文件内容指纹（兼容旧版纯字符串）。"""
    path = _meta_path(data_dir)
    empty = {"sha": "", "dirty_fingerprints": {}, "updated_at": ""}
    if not path.is_file():
        return dict(empty)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(empty)
    envs = data.get("envs") if isinstance(data, dict) else None
    if not isinstance(envs, dict):
        return dict(empty)
    raw = envs.get(env)
    if isinstance(raw, str):
        return {"sha": raw.strip(), "dirty_fingerprints": {}, "updated_at": str(data.get("updated_at") or "")}
    if isinstance(raw, dict):
        fps = raw.get("dirty_fingerprints") or {}
        if not isinstance(fps, dict):
            fps = {}
        return {
            "sha": str(raw.get("sha") or "").strip(),
            "dirty_fingerprints": {str(k): str(v) for k, v in fps.items() if k and v},
            "updated_at": str(raw.get("updated_at") or data.get("updated_at") or ""),
        }
    return dict(empty)


def get_last_deploy_sha(data_dir: Path, env: str) -> str:
    return str(get_last_deploy_record(data_dir, env).get("sha") or "").strip()


def set_last_deploy_sha(
    data_dir: Path,
    env: str,
    sha: str,
    *,
    dirty_fingerprints: dict[str, str] | None = None,
) -> None:
    """写入上次成功部署基线；可附带当时工作区脏文件内容指纹，避免同内容反复强制全量。"""
    path = _meta_path(data_dir)
    lock = _lock_path(data_dir)
    with open(lock, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            data: dict[str, Any] = {"envs": {}}
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        data = {"envs": {}}
                except (OSError, json.JSONDecodeError):
                    data = {"envs": {}}
            envs = data.get("envs")
            if not isinstance(envs, dict):
                envs = {}
            now = datetime.now(timezone.utc).isoformat()
            fps = {
                str(k).replace("\\", "/"): str(v)
                for k, v in (dirty_fingerprints or {}).items()
                if k and v
            }
            envs[str(env)] = {
                "sha": str(sha or "").strip(),
                "dirty_fingerprints": fps,
                "updated_at": now,
            }
            data["envs"] = envs
            data["updated_at"] = now
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
