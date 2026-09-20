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
    resume_commit: bool = False,
    source_gate_job_id: str = "",
    ui_call_id: str = "",
    ui_session_id: str = "",
    user_id: str = "",
    username: str = "",
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

    uid = str(user_id or "").strip()
    uname = str(username or "").strip()
    if not uid:
        try:
            from ..auth import current_user_id, get_active_user

            uid = (current_user_id() or "").strip()
            if not uid:
                active_u = get_active_user() or {}
                uid = str(active_u.get("id") or "").strip()
                if not uname:
                    uname = str(active_u.get("username") or "").strip()
        except Exception:
            pass

    job = job_store.create_job(
        _dd(),
        user_id=uid,
        username=uname,
        thread_id=str(ui_session_id or "").strip(),
        workspace=str(check["path"]),
        message=msg,
        empty_target=bool(check.get("empty")),
        runtime="cursor_local",
        write_scope=write_scope or [],
        brief=brief,
        target_hints=target_hints,
        resume_commit=resume_commit,
        source_gate_job_id=source_gate_job_id,
        ui_call_id=ui_call_id,
        ui_session_id=ui_session_id,
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
    live = job_store.get_job(_dd(), job_id) or job
    from .public_redact import redact_job_public

    tok = str(live.get("stream_token") or "").strip()
    return {
        "ok": True,
        "job_id": job_id,
        # 创建响应下发一次 token（GET job 在强制模式下不再回传）
        "stream_token": tok,
        "job": redact_job_public(live),
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
    from .config import get_config
    from .public_redact import redact_job_public

    pub = redact_job_public(job)
    out: dict[str, Any] = {
        "ok": True,
        "job_id": jid,
        "job": pub,
        "status": pub.get("status"),
        "detail": pub.get("error") or pub.get("status"),
        # 摘要也走脱敏副本，避免 error/progress 绕过
        "reply": _job_summary(pub),
    }
    # 强制 SSE token 时：禁止用 GET job 白嫖 stream_token（只允许创建/确认响应下发一次）
    if not get_config().require_job_stream_token:
        tok = str(job.get("stream_token") or "").strip()
        if tok:
            out["stream_token"] = tok
    return out


def check_job_stream_token(job: dict[str, Any] | None, provided: str) -> dict[str, Any]:
    """SSE 订阅校验。默认不强制；强制时须匹配 job.stream_token。

    无 token 的旧任务：强制模式下仍允许（兼容），避免打断已开跑会话。
    提供了错误 token：一律拒绝。
    """
    from .config import get_config

    cfg = get_config()
    expect = str((job or {}).get("stream_token") or "").strip()
    got = str(provided or "").strip()
    if got and expect and got != expect:
        return {
            "ok": False,
            "detail": "stream_token 无效",
            "code": "job_stream_token_invalid",
        }
    if not cfg.require_job_stream_token:
        return {"ok": True}
    if not expect:
        # 旧任务无 token：放行，避免升级后中断
        return {"ok": True}
    if not got:
        return {
            "ok": False,
            "detail": "订阅进度须带 stream_token",
            "code": "job_stream_token_missing",
        }
    return {"ok": True}


def list_recent_jobs(*, limit: int = 80, ui_call_id: str = "") -> dict[str, Any]:
    """列出本机写码任务（按更新时间倒序），供历史核对；可按 DSH callId 过滤。"""
    from ..space.redact import redact_text

    cid = str(ui_call_id or "").strip()
    if cid:
        rows = job_store.find_jobs_by_ui_call_id(_dd(), cid, limit=max(1, min(int(limit or 80), 200)))
    else:
        cap = max(1, min(int(limit or 80), 200))
        rows = job_store.list_jobs(_dd())[:cap]
    slim: list[dict[str, Any]] = []
    for j in rows:
        brief = j.get("brief") if isinstance(j.get("brief"), dict) else {}
        req = str(
            j.get("requirement")
            or j.get("message")
            or brief.get("original_goal")
            or brief.get("summary")
            or ""
        ).strip()
        # messages[0] 常是用户需求
        if not req and isinstance(j.get("messages"), list) and j["messages"]:
            req = str((j["messages"][0] or {}).get("content") or "").strip()
        req_pub, _ = redact_text(req[:160], max_chars=200)
        err_raw = str(j.get("error") or "")
        err_pub, _ = redact_text(err_raw, max_chars=400) if err_raw else ("", False)
        slim.append(
            {
                "id": j.get("id"),
                "status": j.get("status"),
                "workspace": j.get("workspace"),
                "requirement": req_pub,
                "ui_call_id": j.get("ui_call_id"),
                "ui_session_id": j.get("ui_session_id"),
                "created_at": j.get("created_at"),
                "updated_at": j.get("updated_at"),
                "error": err_pub or None,
            }
        )
    return {
        "ok": True,
        "count": len(slim),
        "jobs": slim,
        "data_dir": str(_dd() / "local_dev"),
    }


def cancel(job_id: str) -> dict[str, Any]:
    jid = (job_id or "").strip()
    if not jid:
        return {"ok": False, "detail": "job_id 不能为空"}
    job = job_store.request_cancel(_dd(), jid, reason="用户取消")
    if not job:
        return {"ok": False, "detail": f"找不到任务 {jid}", "reply": f"找不到任务 {jid}"}
    from .public_redact import redact_job_public

    return {
        "ok": True,
        "job_id": jid,
        "job": redact_job_public(job),
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
        defer_s = [str(x).replace("\\", "/") for x in deferred]
        wiring_miss = any(
            ("/config/" in p)
            or ("/router/" in p)
            or ("/layouts/" in p)
            or ("reportFeatures" in p)
            or ("reportIcons" in p)
            for p in defer_s
        )
        prefix = (
            "⚠ 含菜单/路由配置未同步：浏览器可能看不到新菜单，勿只信交付「已上菜单」。"
            if wiring_miss
            else "⚠️ 未同步文件可能导致页面报错（如 Vite Failed to resolve import）。"
        )
        lines.append(
            prefix
            + "未同步："
            + "、".join(str(x) for x in deferred[:8])
            + ("…" if len(deferred) > 8 else "")
            + "。请缩小需求或重新写码并确认同步完成。"
        )
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
