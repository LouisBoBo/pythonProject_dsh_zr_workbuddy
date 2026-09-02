"""对外命令面：供 cli_ops / HTTP 调用（与 feature runEngine 同源）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import jobs as job_store
from .config import availability, get_config
from .service import default_data_dir, run_job, start_job_background
from .workspace import validate_workspace

FEATURE_ID = "code-dev"


def _dd() -> Path:
    return default_data_dir()


def status() -> dict[str, Any]:
    avail = availability()
    cfg = get_config()
    running = job_store.count_jobs_by_status(_dd(), {"queued", "running"})
    return {
        "ok": True,
        "feature": FEATURE_ID,
        "code_dev": avail,
        "max_concurrent": cfg.max_concurrent,
        "active_jobs": running,
        "data_dir": str(_dd() / "local_dev"),
        "reply": avail.get("detail") or "",
        "detail": avail.get("detail") or "",
    }


def check_workspace(path: str) -> dict[str, Any]:
    out = validate_workspace(path)
    out["ok"] = bool(out.get("ok"))
    if out["ok"]:
        out["detail"] = f"目录可用：{out.get('path')}"
        out["reply"] = out["detail"]
    else:
        out["detail"] = out.get("error") or "目录不可用"
        out["reply"] = out["detail"]
    return out


def start(
    *,
    workspace: str,
    message: str,
    write_scope: list[str] | None = None,
    sync: bool = False,
    brief: dict[str, Any] | None = None,
    target_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建并启动 Job。sync=True 时前台跑完（测试用）；默认后台。"""
    cfg = get_config()
    if not cfg.enabled:
        return {
            "ok": False,
            "detail": "本机写码未开启：请到引擎「配置中心 → 写码车道」勾选开启并保存",
            "reply": "本机写码未开启（请到配置中心开启）",
        }

    avail = availability()
    if not avail.get("ok"):
        return {
            "ok": False,
            "detail": avail.get("detail") or "Cursor Local 未就绪",
            "reply": avail.get("detail") or "Cursor Local 未就绪",
        }

    check = validate_workspace(workspace)
    if not check.get("ok"):
        return {
            "ok": False,
            "detail": check.get("error") or "目录无效",
            "reply": check.get("error") or "目录无效",
            "workspace": check,
        }

    msg = (message or "").strip()
    if not msg:
        return {"ok": False, "detail": "需求描述不能为空", "reply": "需求描述不能为空"}
    if len(msg) > 12000:
        return {"ok": False, "detail": "需求描述过长", "reply": "需求描述过长（上限 12000 字）"}

    active = job_store.count_jobs_by_status(_dd(), {"queued", "running"})
    if active >= cfg.max_concurrent:
        return {
            "ok": False,
            "detail": f"已有 {active} 个进行中任务，上限 {cfg.max_concurrent}",
            "reply": f"进行中任务已达上限（{cfg.max_concurrent}）",
        }

    job = job_store.create_job(
        _dd(),
        user_id="",
        username="",
        thread_id="",
        workspace=str(check["path"]),
        message=msg,
        empty_target=bool(check.get("empty")),
        runtime="cursor_local",
        write_scope=write_scope or [],
        brief=brief,
        target_hints=target_hints,
    )
    job_id = str(job["id"])
    if sync:
        # 测试：先 claim 再同步跑
        claimed = job_store.try_claim_job(_dd(), job_id) or job
        final = run_job(_dd(), claimed)
        return {
            "ok": str(final.get("status") or "") == "succeeded",
            "job_id": job_id,
            "job": final,
            "detail": final.get("error") or final.get("status"),
            "reply": _job_summary(final),
        }

    start_job_background(_dd(), job_id)
    return {
        "ok": True,
        "job_id": job_id,
        "job": job_store.get_job(_dd(), job_id) or job,
        "detail": "任务已排队/启动，请用 code-dev-job 查询",
        "reply": f"已启动写码任务 {job_id}，请稍后查询状态。",
    }


def get_job(job_id: str) -> dict[str, Any]:
    jid = (job_id or "").strip()
    if not jid:
        return {"ok": False, "detail": "job_id 不能为空", "reply": "job_id 不能为空"}
    job = job_store.get_job(_dd(), jid)
    if not job:
        return {"ok": False, "detail": f"找不到任务 {jid}", "reply": f"找不到任务 {jid}"}
    return {
        "ok": True,
        "job_id": jid,
        "job": job,
        "status": job.get("status"),
        "detail": job.get("error") or job.get("status"),
        "reply": _job_summary(job),
    }


def cancel(job_id: str) -> dict[str, Any]:
    jid = (job_id or "").strip()
    if not jid:
        return {"ok": False, "detail": "job_id 不能为空"}
    job = job_store.request_cancel(_dd(), jid, reason="用户取消")
    if not job:
        return {"ok": False, "detail": f"找不到任务 {jid}", "reply": f"找不到任务 {jid}"}
    return {
        "ok": True,
        "job_id": jid,
        "job": job,
        "detail": "已请求取消",
        "reply": f"已请求取消任务 {jid}",
    }


def _job_summary(job: dict[str, Any]) -> str:
    st = str(job.get("status") or "")
    jid = str(job.get("id") or "")
    err = str(job.get("error") or "").strip()
    synced = job.get("synced_files") or []
    deferred = job.get("deferred_files") or []
    progress = str(job.get("progress") or "").strip()
    lines = [f"任务 {jid}：{st}"]
    if progress and st in {"queued", "running"}:
        lines.append(f"进度：{progress}")
    if err:
        lines.append(f"错误：{err}")
    if synced:
        lines.append(f"已同步 {len(synced)} 个文件：" + "、".join(synced[:12]))
        if len(synced) > 12:
            lines.append(f"…共 {len(synced)} 个")
    if deferred:
        lines.append(f"范围外未同步 {len(deferred)} 个")
    # 终态附助手说明（Cursor 改码小结）
    if st in {"succeeded", "failed", "cancelled"}:
        for m in reversed(job.get("messages") or []):
            if m.get("role") == "assistant":
                body = str(m.get("content") or "").strip()
                if body:
                    lines.append("")
                    lines.append(body[:4000])
                break
    return "\n".join(lines)


def format_job_done_reply(job: dict[str, Any]) -> str:
    """确认后进度卡片终态用的完整回复。"""
    return _job_summary(job)
