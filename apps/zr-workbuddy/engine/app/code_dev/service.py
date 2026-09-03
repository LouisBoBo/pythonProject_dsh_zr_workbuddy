"""本机写码 Job 执行：沙箱 → Cursor Local → 快照 diff → 受限同步（无提交/预览）。"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from . import jobs as job_store
from .config import CodeDevConfig, get_config
from .cursor_agent import build_prompt, run_cursor_local_agent
from .fs_snapshot import diff_snapshots, snapshot_sandbox
from .path_scope import partition_by_scope
from .sandbox import prepare_sandbox, sync_changed_to_target
from .workspace import validate_workspace

Sink = Callable[[dict[str, Any]], None]

_bg_lock = threading.Lock()
_bg_threads: dict[str, threading.Thread] = {}


def _data_dir() -> Path:
    # engine/app/code_dev → engine/data
    return Path(__file__).resolve().parents[2] / "data"


def _emit(sink: Sink | None, event: dict[str, Any]) -> None:
    if sink:
        try:
            sink(event)
        except Exception:
            pass


def run_job(
    data_dir: Path,
    job: dict[str, Any],
    *,
    sink: Sink | None = None,
    cfg: CodeDevConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or get_config()
    job_id = str(job.get("id") or "")
    if not job_id:
        raise ValueError("job id missing")

    if not cfg.enabled:
        err = "本机写码未开启（config.yaml → code_dev.enabled）"
        job_store.update_job(data_dir, job_id, status="failed", error=err)
        _emit(sink, {"type": "error", "message": err})
        return job_store.get_job(data_dir, job_id) or job

    job_store.update_job(data_dir, job_id, status="running", error=None, runtime="cursor_local")
    _emit(sink, {"type": "status", "text": "本机 Cursor Local 写码开始", "phase": "start"})

    workspace = str(job.get("workspace") or "").strip()
    check = validate_workspace(workspace)
    if not check.get("ok"):
        err = check.get("error") or "目标目录无效"
        job_store.update_job(data_dir, job_id, status="failed", error=err)
        _emit(sink, {"type": "error", "message": err})
        return job_store.get_job(data_dir, job_id) or job

    target = Path(check["path"])
    empty_target = bool(check.get("empty"))
    job_store.update_job(data_dir, job_id, empty_target=empty_target)

    def step(title: str, *, sid: str, state: str = "running") -> None:
        _emit(sink, {"type": "step", "id": sid, "state": state, "title": title})

    try:
        if job_store.is_cancel_requested(data_dir, job_id):
            raise RuntimeError("任务已取消")

        step("准备沙箱", sid="sandbox-prep")
        scope_for_copy = list(job.get("write_scope") or [])
        meta = prepare_sandbox(
            data_dir,
            job_id,
            target,
            empty_target=empty_target,
            cfg=cfg,
            on_progress=lambda t: step(t, sid="sandbox-prep"),
            include_rels=scope_for_copy or None,
        )
        sandbox_path = Path(meta["sandbox"])
        job_store.update_job(
            data_dir,
            job_id,
            sandbox_path=str(sandbox_path),
            sandbox_mode=meta.get("mode"),
            sandbox_copied_files=meta.get("copied_files"),
        )
        step(
            f"沙箱就绪（{meta.get('mode') or 'copy'} · {meta.get('copied_files') or 0} 文件）",
            sid="sandbox-prep",
            state="done",
        )

        requirement = ""
        for m in reversed(job.get("messages") or []):
            if m.get("role") == "user":
                requirement = str(m.get("content") or "")
                break
        if not requirement.strip():
            raise RuntimeError("需求为空")

        before = snapshot_sandbox(sandbox_path)
        prompt = build_prompt(
            requirement=requirement,
            workspace_hint=str(target),
            empty_target=empty_target,
        )
        step("Cursor 在沙箱内改码…", sid="agent-loop")
        cre = run_cursor_local_agent(
            sandbox=sandbox_path,
            prompt=prompt,
            sink=sink,
            step=step,
            is_cancel_requested=lambda: job_store.is_cancel_requested(data_dir, job_id),
            timeout_sec=cfg.cursor_timeout_sec,
        )
        if not cre.get("ok"):
            raise RuntimeError(cre.get("error") or "Cursor 本机写码失败")

        step("沙箱内改码完成", sid="agent-loop", state="done")

        assistant_text = str(cre.get("text") or "")
        agent_id = str(cre.get("agent_id") or "")
        if agent_id:
            job_store.update_job(data_dir, job_id, agent_id=agent_id)

        after = snapshot_sandbox(sandbox_path)
        changed = diff_snapshots(before, after)
        if len(changed) > cfg.max_changed_files:
            raise RuntimeError(
                f"变更文件过多（{len(changed)}>{cfg.max_changed_files}），已中止同步以防误伤"
            )

        scope = job.get("write_scope") or []
        inside, outside = partition_by_scope(changed, scope)
        # P0：范围外文件不同步（记入 deferred），不进入 awaiting_scope（无 SPA 卡）
        synced: list[str] = []
        if inside:
            step(f"同步 {len(inside)} 个文件到目标目录…", sid="sync")
            synced = sync_changed_to_target(sandbox_path, target, inside, cfg=cfg)
            step("同步完成", sid="sync", state="done")
        elif changed and not outside:
            # 空变更
            pass
        elif outside and not inside:
            step("变更均在写范围外，已跳过同步", sid="sync", state="done")

        mismatch = ""
        from .brief import append_sync_mismatch_warning

        mismatch = append_sync_mismatch_warning(
            {
                "messages": job.get("messages") or [],
                "synced_files": synced,
                "brief": job.get("brief"),
            }
        )

        job_store.update_job(
            data_dir,
            job_id,
            status="succeeded",
            error=None,
            changed_files=changed,
            synced_files=synced,
            deferred_files=outside,
            sync_mismatch=mismatch or None,
        )
        assistant_body = assistant_text + (
            f"\n\n【同步】{len(synced)} 个文件"
            + (f"；范围外未同步 {len(outside)} 个" if outside else "")
            + (f"\n\n{mismatch}" if mismatch else "")
        )
        job_store.append_message(
            data_dir,
            job_id,
            role="assistant",
            content=assistant_body,
        )
        _emit(
            sink,
            {
                "type": "done",
                "ok": True,
                "synced_files": synced,
                "deferred_files": outside,
            },
        )
        return job_store.get_job(data_dir, job_id) or job

    except Exception as exc:  # noqa: BLE001
        err = str(exc) or type(exc).__name__
        if job_store.is_cancel_requested(data_dir, job_id):
            job_store.update_job(data_dir, job_id, status="cancelled", error=err)
        else:
            job_store.update_job(data_dir, job_id, status="failed", error=err)
        _emit(sink, {"type": "error", "message": err})
        return job_store.get_job(data_dir, job_id) or job


def start_job_background(data_dir: Path, job_id: str) -> None:
    """后台线程跑 Job；同 id 不重复启动。进度经 sink 写入 job 供面板轮询/SSE。"""

    def _sink(event: dict[str, Any]) -> None:
        try:
            job_store.record_event(data_dir, job_id, event)
        except Exception:
            pass

    def _run() -> None:
        try:
            claimed = job_store.try_claim_job(data_dir, job_id)
            if not claimed:
                return
            run_job(data_dir, claimed, sink=_sink)
        finally:
            with _bg_lock:
                _bg_threads.pop(job_id, None)

    with _bg_lock:
        t_old = _bg_threads.get(job_id)
        if t_old and t_old.is_alive():
            return
        t = threading.Thread(target=_run, name=f"code-dev-{job_id}", daemon=True)
        _bg_threads[job_id] = t
        t.start()


def default_data_dir() -> Path:
    return _data_dir()
