"""本机写码任务落盘。"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_lock = threading.Lock()

STATUSES = frozenset(
    {
        "queued",
        "running",
        "awaiting_scope",
        "awaiting_commit",
        "succeeded",
        "failed",
        "cancelled",
    }
)


def jobs_dir(data_dir: Path) -> Path:
    d = Path(data_dir) / "local_dev" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _job_path(data_dir: Path, job_id: str) -> Path:
    safe = "".join(c for c in job_id if c.isalnum() or c in "-_")
    if not safe or safe != job_id:
        raise ValueError("invalid job_id")
    return jobs_dir(data_dir) / f"{safe}.json"


def new_job_id() -> str:
    return f"ldj-{uuid.uuid4().hex[:16]}"


def create_job(
    data_dir: Path,
    *,
    user_id: str | int | None,
    username: str | None,
    thread_id: str,
    workspace: str,
    message: str,
    empty_target: bool = False,
    runtime: str | None = None,
    write_scope: list[str] | None = None,
    file_paths: list[str] | None = None,
    brief: dict[str, Any] | None = None,
    target_hints: dict[str, Any] | None = None,
    resume_commit: bool = False,
    source_gate_job_id: str = "",
) -> dict[str, Any]:
    now = int(time.time())
    rt = (runtime or "cursor_local").strip() or "cursor_local"
    if rt not in {"cursor_local", "local_sandbox"}:
        rt = "cursor_local"
    from .path_scope import normalize_write_scope

    scope = normalize_write_scope(write_scope)
    paths = [str(p).strip() for p in (file_paths or []) if str(p).strip()][:8]
    notes = list((brief or {}).get("notes") or []) if isinstance(brief, dict) else []
    gate_from_notes = any("source=code_commit_gate" in str(n) for n in notes)
    resume = bool(resume_commit) or gate_from_notes or bool(scope)
    job: dict[str, Any] = {
        "id": new_job_id(),
        "user_id": "" if user_id is None else str(user_id),
        "username": username or "",
        "thread_id": thread_id or "",
        "workspace": workspace,
        "empty_target": bool(empty_target),
        "status": "queued",
        "messages": [{"role": "user", "content": message, "at": now}],
        "sandbox_path": None,
        "changed_files": [],
        "synced_files": [],
        "write_scope": scope,
        "file_paths": paths,
        "deferred_files": [],
        "scope_decision": None,
        "commit_decision": None,
        "commit_gate": None,
        "commit_result": None,
        "preview_url": None,
        "preview": None,
        "error": None,
        "cancel_requested": False,
        "runtime": rt,
        "agent_id": None,
        "progress": "",
        "steps": [],
        "live_text": "",
        "events": [],
        "brief": brief or {},
        "target_hints": target_hints or {},
        "sync_mismatch": None,
        "resume_commit": resume,
        "source_gate_job_id": (source_gate_job_id or "").strip() or None,
        "created_at": now,
        "updated_at": now,
    }
    with _lock:
        path = _job_path(data_dir, job["id"])
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def get_job(data_dir: Path, job_id: str) -> dict[str, Any] | None:
    try:
        path = _job_path(data_dir, job_id)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def update_job(data_dir: Path, job_id: str, **fields: Any) -> dict[str, Any] | None:
    with _lock:
        job = get_job(data_dir, job_id)
        if not job:
            return None
        # 范围确认：仅 awaiting_scope 且尚未决策时可写入（防并发双写）
        if "scope_decision" in fields:
            if str(job.get("status") or "") != "awaiting_scope":
                return job
            if job.get("scope_decision") in {"include", "skip"}:
                return job
            decision = fields.get("scope_decision")
            if decision not in {"include", "skip"}:
                fields = {k: v for k, v in fields.items() if k != "scope_decision"}
                if not fields:
                    return job
        # 提交确认：仅 awaiting_commit 且尚未决策（None 表示网络失败重试清空）
        if "commit_decision" in fields:
            decision = fields.get("commit_decision")
            if decision is None:
                if str(job.get("status") or "") != "awaiting_commit" and fields.get("status") != "awaiting_commit":
                    fields = {k: v for k, v in fields.items() if k != "commit_decision"}
            elif str(job.get("status") or "") != "awaiting_commit":
                # succeeded 等态在 push 重试时会先 reopen 为 awaiting_commit
                if fields.get("status") != "awaiting_commit":
                    return job
            elif job.get("commit_decision") in {"commit", "skip"}:
                if decision is not None:
                    return job
            elif decision not in {"commit", "skip"}:
                fields = {k: v for k, v in fields.items() if k != "commit_decision"}
            if not fields:
                return job
        cur_status = str(job.get("status") or "")
        new_status = fields.get("status")
        # 已取消：禁止再写成 queued/running/succeeded/failed（后台线程收尾不得覆盖）
        if cur_status == "cancelled" and new_status is not None and str(new_status) != "cancelled":
            fields = {k: v for k, v in fields.items() if k != "status"}
            if not fields:
                return job
        # 用户已点取消但状态尚未落到 cancelled 时，同样禁止成功收尾
        if job.get("cancel_requested") and new_status is not None:
            if str(new_status) in {"queued", "running", "succeeded", "awaiting_commit"}:
                fields = {k: v for k, v in fields.items() if k != "status"}
                if not fields:
                    return job
        for k, v in fields.items():
            job[k] = v
        job["updated_at"] = int(time.time())
        path = _job_path(data_dir, job_id)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return job


def record_event(data_dir: Path, job_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
    """写入进度事件（供面板轮询/SSE）；截断 events，更新 progress / steps / live_text。"""
    with _lock:
        job = get_job(data_dir, job_id)
        if not job:
            return None
        ev = dict(event or {})
        ev.setdefault("at", int(time.time()))
        events = list(job.get("events") or [])
        events.append(ev)
        if len(events) > 240:
            events = events[-240:]
        job["events"] = events

        et = str(ev.get("type") or "")
        if et == "status":
            job["progress"] = str(ev.get("text") or ev.get("detail") or job.get("progress") or "")
        elif et == "step":
            title = str(ev.get("title") or "").strip()
            sid = str(ev.get("id") or title or "step")
            state = str(ev.get("state") or "running")
            steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
            found = False
            for s in steps:
                if str(s.get("id") or "") == sid:
                    s["title"] = title or s.get("title")
                    s["state"] = state
                    found = True
                    break
            if not found and title:
                steps.append({"id": sid, "title": title, "state": state})
            job["steps"] = steps[-40:]
            if title:
                job["progress"] = title
        elif et == "token":
            piece = str(ev.get("text") or "")
            if piece:
                job["live_text"] = str(job.get("live_text") or "") + piece
                if len(job["live_text"]) > 12000:
                    job["live_text"] = job["live_text"][-12000:]
        elif et == "replace_text":
            job["live_text"] = str(ev.get("text") or "")[:12000]
        elif et == "error":
            job["progress"] = str(ev.get("message") or ev.get("detail") or "出错")

        job["updated_at"] = int(time.time())
        path = _job_path(data_dir, job_id)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return job


def try_claim_job(data_dir: Path, job_id: str) -> dict[str, Any] | None:
    """原子抢占：queued|failed → running。并发 SSE 时仅一个成功，其余返回 None。"""
    with _lock:
        job = get_job(data_dir, job_id)
        if not job:
            return None
        if job.get("cancel_requested") or str(job.get("status") or "") == "cancelled":
            return None
        st = str(job.get("status") or "")
        if st not in {"queued", "failed"}:
            return None
        job["status"] = "running"
        job["error"] = None
        job["cancel_requested"] = False
        job["updated_at"] = int(time.time())
        path = _job_path(data_dir, job_id)
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        return job


def request_cancel(data_dir: Path, job_id: str, reason: str = "用户取消") -> dict[str, Any] | None:
    return update_job(
        data_dir,
        job_id,
        cancel_requested=True,
        error=reason,
        status="cancelled",
    )


def is_cancel_requested(data_dir: Path, job_id: str) -> bool:
    job = get_job(data_dir, job_id)
    return bool(job and job.get("cancel_requested"))


def count_jobs_by_status(
    data_dir: Path,
    statuses: set[str] | frozenset[str],
    *,
    user_id: str | None = None,
) -> int:
    n = 0
    for p in jobs_dir(data_dir).glob("*.json"):
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if job.get("status") not in statuses:
            continue
        if user_id is not None and str(job.get("user_id") or "") != str(user_id):
            continue
        n += 1
    return n


def list_jobs(
    data_dir: Path,
    *,
    statuses: set[str] | frozenset[str] | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in jobs_dir(data_dir).glob("*.json"):
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if statuses is not None and job.get("status") not in statuses:
            continue
        if user_id is not None and str(job.get("user_id") or "") != str(user_id):
            continue
        out.append(job)
    out.sort(key=lambda j: int(j.get("updated_at") or 0), reverse=True)
    return out


def write_job_document(data_dir: Path, job: dict[str, Any]) -> dict[str, Any]:
    """原子写入完整 job 文档（供 commit_batch 等旁路创建，不经 create_job）。"""
    job_id = str(job.get("id") or "")
    if not job_id:
        raise ValueError("job id missing")
    with _lock:
        path = _job_path(data_dir, job_id)
        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = dict(job)
        payload["updated_at"] = int(time.time())
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return payload


def append_message(data_dir: Path, job_id: str, *, role: str, content: str) -> dict[str, Any] | None:
    with _lock:
        job = get_job(data_dir, job_id)
        if not job:
            return None
        msgs = list(job.get("messages") or [])
        msgs.append({"role": role, "content": content, "at": int(time.time())})
        job["messages"] = msgs
        job["updated_at"] = int(time.time())
        path = _job_path(data_dir, job_id)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return job
