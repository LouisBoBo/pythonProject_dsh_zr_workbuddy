"""提交车道命令面：CLI / HTTP / feature 同源。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import availability, get_config
from .gate import run_commit_review_gate
from .git_ops import (
    commit_synced_files,
    draft_chinese_commit_message,
    filter_pending_commit_files,
    inspect_git_repo,
    is_push_retry_needed,
    push_retry_hint,
    resolve_work_branch,
    validate_branch_name,
    validate_chinese_commit_message,
    _push_work_branch,
)
from .store import (
    claim_job_for_commit,
    latest_blocked_job,
    load_job,
    new_job_id,
    save_job,
    supersede_awaiting_for_workspace,
    update_job,
)

FEATURE_ID = "code-commit"


def default_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def status() -> dict[str, Any]:
    avail = availability()
    cfg = get_config()
    return {
        "ok": True,
        "feature": FEATURE_ID,
        "code_commit": avail,
        "default_push": cfg.default_push,
        "work_branch": cfg.work_branch,
        "remote_name": cfg.remote_name,
        "max_files": cfg.max_files,
        "reply": avail.get("detail") or "",
        "detail": avail.get("detail") or "",
    }


def check_path(path: str) -> dict[str, Any]:
    """校验本机 git 工程目录。"""
    raw = (path or "").strip()
    if not raw:
        return {"ok": False, "detail": "路径不能为空", "reply": "路径不能为空"}
    try:
        from ..code_dev.workspace import validate_workspace

        ws = validate_workspace(raw)
        if not ws.get("ok"):
            return {
                "ok": False,
                "detail": ws.get("error") or "路径不可用",
                "reply": ws.get("error") or "路径不可用",
                "path": ws.get("path") or raw,
            }
        root = Path(ws["path"])
    except Exception:
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            return {"ok": False, "detail": "目录不存在", "reply": "目录不存在", "path": str(root)}

    info = inspect_git_repo(root)
    if not info.get("is_git"):
        return {
            "ok": False,
            "detail": info.get("reason") or "不是 git 仓库",
            "reply": info.get("reason") or "不是 git 仓库",
            "path": str(root),
        }
    branch_info = preview_commit_branch(str(root))
    return {
        "ok": True,
        "path": str(root),
        "git": info,
        **branch_info,
        "detail": f"Git 仓库可用：{root}（当前分支 {info.get('current_branch') or '?'}）",
        "reply": f"路径可用：{root}",
    }


def preview_commit_branch(
    workspace: str = "",
    *,
    user_branch: str = "",
) -> dict[str, Any]:
    """确认卡分支预览：当前分支 → 配置中心 → 需用户填写（不自动生成 anon）。"""
    cfg = get_config()
    config_branch = (cfg.work_branch or "").strip().strip("/")
    current_branch = ""
    on_protected = False
    root_s = (workspace or "").strip()
    if root_s:
        try:
            root = Path(root_s).expanduser().resolve()
            if root.is_dir():
                info = inspect_git_repo(root)
                current_branch = str(info.get("current_branch") or "").strip()
                on_protected = bool(info.get("on_protected"))
        except Exception:  # noqa: BLE001
            pass

    typed = (user_branch or "").strip().strip("/")
    if typed:
        ok, err = validate_branch_name(typed)
        return {
            "work_branch": typed if ok else "",
            "current_branch": current_branch,
            "config_branch": config_branch,
            "branch_source": "user",
            "need_user_branch": not ok,
            "branch_hint": "" if ok else (err or "请填写合法分支名"),
            "on_protected": on_protected,
        }

    if current_branch and not on_protected:
        ok, err = validate_branch_name(current_branch)
        if ok:
            return {
                "work_branch": current_branch,
                "current_branch": current_branch,
                "config_branch": config_branch,
                "branch_source": "current",
                "need_user_branch": False,
                "branch_hint": f"使用仓库当前分支「{current_branch}」",
                "on_protected": False,
            }

    if config_branch:
        ok, err = validate_branch_name(config_branch)
        if ok:
            hint = f"使用配置中心工作分支「{config_branch}」"
            if on_protected and current_branch:
                hint = (
                    f"当前在保护分支「{current_branch}」，"
                    f"已改用配置中心分支「{config_branch}」"
                )
            return {
                "work_branch": config_branch,
                "current_branch": current_branch,
                "config_branch": config_branch,
                "branch_source": "config",
                "need_user_branch": False,
                "branch_hint": hint,
                "on_protected": on_protected,
            }

    if on_protected and current_branch:
        hint = (
            f"当前在保护分支「{current_branch}」，禁止直接提交。"
            "请填写功能分支名，或到配置中心设置工作分支。"
        )
    elif not root_s:
        hint = "请先选择工程目录；分支将自动填入当前分支或配置中心分支。"
    else:
        hint = "未能识别可提交分支，请手动填写要提交的分支名。"
    return {
        "work_branch": "",
        "current_branch": current_branch,
        "config_branch": config_branch,
        "branch_source": "none",
        "need_user_branch": True,
        "branch_hint": hint,
        "on_protected": on_protected,
    }


def _recent_synced_files(workspace: str) -> list[str]:
    """从近期写码 Job 收集同步文件作为优先池（可为空）。"""
    try:
        from ..code_dev.jobs import list_jobs

        jobs = (list_jobs(default_data_dir()) or [])[:20]
    except Exception:
        return []
    root = str(Path(workspace).expanduser().resolve())
    out: list[str] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        jws = str(job.get("workspace") or "").strip()
        try:
            if jws and str(Path(jws).expanduser().resolve()) != root:
                continue
        except OSError:
            continue
        for f in job.get("synced_files") or []:
            rel = str(f).replace("\\", "/").strip()
            if rel and rel not in out:
                out.append(rel)
        if len(out) >= 120:
            break
    return out


def prepare(
    workspace: str,
    *,
    files: list[str] | None = None,
    work_branch: str = "",
) -> dict[str, Any]:
    """列出待提交文件（同步池仍脏 ∪ Git 可提交脏文件）。"""
    cfg = get_config()
    if not cfg.enabled:
        return {
            "ok": False,
            "detail": "提交车道未开启",
            "reply": "请用浏览器打开 http://127.0.0.1:8000 → 配置中心 → 第 7 步「提交车道」开启并保存",
        }
    check = check_path(workspace)
    if not check.get("ok"):
        return check

    root = Path(check["path"])
    synced = list(files) if files else _recent_synced_files(str(root))
    filtered = filter_pending_commit_files(root, synced)
    pending = list(filtered.get("pending_files") or [])[: cfg.max_files]
    draft = draft_chinese_commit_message(files=pending)
    git_info = check.get("git") or {}
    cur_branch = str(git_info.get("current_branch") or "").strip()
    br = preview_commit_branch(str(root), user_branch=work_branch)
    if br.get("need_user_branch") or not br.get("work_branch"):
        return {
            "ok": False,
            "detail": br.get("branch_hint") or "请填写要提交的分支",
            "reply": br.get("branch_hint") or "请填写要提交的分支",
            "current_branch": cur_branch,
            "config_branch": br.get("config_branch") or "",
            "work_branch": "",
            "need_user_branch": True,
            "branch_hint": br.get("branch_hint") or "",
            "branch_source": br.get("branch_source") or "none",
            "git": git_info,
        }
    chosen = str(br.get("work_branch") or "")
    ok_br, err_br = validate_branch_name(chosen)
    if not ok_br:
        return {
            "ok": False,
            "detail": err_br,
            "reply": err_br,
            "current_branch": cur_branch,
            "work_branch": chosen,
            "need_user_branch": True,
            "branch_hint": err_br,
            "git": git_info,
        }
    return {
        "ok": True,
        "workspace": str(root),
        "files": pending,
        "pending_files": pending,
        "pending_total": len(pending),
        "work_branch": chosen,
        "current_branch": cur_branch,
        "config_branch": br.get("config_branch") or "",
        "branch_source": br.get("branch_source") or "",
        "branch_hint": br.get("branch_hint") or "",
        "default_push": cfg.default_push,
        "draft_message": draft,
        "git": git_info,
        "scope_note": filtered.get("scope_note"),
        "pending_source": filtered.get("pending_source"),
        "reply": (
            f"待提交 {len(pending)} 个文件（分支 {chosen}）"
            if pending
            else "没有待提交变更（Git 工作区干净，或仅有日志/敏感等不可提交文件）"
        ),
        "detail": filtered.get("scope_note") or "",
    }


def start_gate(
    workspace: str,
    *,
    files: list[str] | None = None,
    work_branch: str = "",
) -> dict[str, Any]:
    """列出文件 → 跑门禁 → 落盘 Job。阻断则 status=blocked，不可 confirm。"""
    cfg = get_config()
    if not cfg.enabled:
        return {
            "ok": False,
            "detail": "提交车道未开启",
            "reply": "请用浏览器打开 http://127.0.0.1:8000 → 配置中心 → 第 7 步「提交车道」开启并保存",
            "can_commit": False,
        }

    prep = prepare(workspace, files=files, work_branch=work_branch)
    if not prep.get("ok"):
        return {**prep, "can_commit": False}

    pending = list(prep.get("pending_files") or [])
    if not pending:
        return {
            **prep,
            "ok": False,
            "can_commit": False,
            "detail": "没有可提交的文件",
            "reply": prep.get("reply") or "没有可提交的文件",
            "findings": [],
        }

    gate = run_commit_review_gate(
        prep["workspace"],
        pending,
        allow_blocked_override=cfg.allow_blocked,
        use_skill_review=cfg.use_skill_review,
    )
    can_commit = bool(gate.get("can_commit"))
    job_id = new_job_id()
    # 作废同仓库旧确认卡，防止过期 job 仍可提交
    supersede_awaiting_for_workspace(default_data_dir(), prep["workspace"], keep_id=job_id)
    job = {
        "id": job_id,
        "feature": FEATURE_ID,
        "status": "awaiting_commit" if can_commit else "blocked",
        "workspace": prep["workspace"],
        "files": pending,
        "work_branch": prep.get("work_branch"),
        "default_push": prep.get("default_push"),
        "draft_message": prep.get("draft_message"),
        "gate": {
            "can_commit": can_commit,
            "summary": gate.get("summary"),
            "verdict": gate.get("verdict"),
            "blocking_count": gate.get("blocking_count"),
            "warning_count": gate.get("warning_count"),
            "provider": gate.get("provider"),
            "review_method": gate.get("review_method"),
        },
        "findings": gate.get("findings") or [],
        "file_scans": gate.get("file_scans") or [],
        "commit_result": None,
    }
    save_job(default_data_dir(), job)

    blocking = [f for f in (gate.get("findings") or []) if f.get("blocking")]
    reply = gate.get("summary") or ""
    if not can_commit:
        reply = (
            f"{reply}\n\n存在阻断项，请先修复后再提交。"
            + (
                "\n" + "\n".join(
                    f"- [{f.get('severity')}] {f.get('path')}: {f.get('message')}"
                    for f in blocking[:10]
                )
            )
        )
    else:
        reply = f"{reply}\n\n请在确认卡填写中文说明并确认后才会执行 git commit/push。"

    return {
        "ok": True,
        "job_id": job_id,
        "status": job["status"],
        "workspace": prep["workspace"],
        "files": pending,
        "pending_total": len(pending),
        "work_branch": prep.get("work_branch"),
        "default_push": prep.get("default_push"),
        "draft_message": prep.get("draft_message"),
        "can_commit": can_commit,
        "findings": gate.get("findings") or [],
        "blocking_count": gate.get("blocking_count") or 0,
        "warning_count": gate.get("warning_count") or 0,
        "summary": gate.get("summary"),
        "verdict": gate.get("verdict"),
        "review_method": gate.get("review_method"),
        "provider": gate.get("provider"),
        "scope_note": prep.get("scope_note"),
        "reply": reply,
        "detail": gate.get("summary") or "",
        "code_commit_ui": _build_confirm_ui(job) if can_commit else None,
    }


def _build_confirm_ui(job: dict[str, Any]) -> dict[str, Any]:
    cfg = get_config()
    findings = job.get("findings") or []
    blocking = [f for f in findings if f.get("blocking")]
    warnings = [f for f in findings if not f.get("blocking")]
    return {
        "kind": "confirm",
        "status": "pending",
        "job_id": job.get("id"),
        "workspace": job.get("workspace") or "",
        "files": job.get("files") or [],
        "work_branch": job.get("work_branch") or "",
        "message": job.get("draft_message") or "",
        "push": bool(job.get("default_push", cfg.default_push)),
        "findings": findings,
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "summary": (job.get("gate") or {}).get("summary") or "",
        "hint": "确认后才会 git commit / push",
        "desc": (
            f"门禁已通过。将提交到分支「{job.get('work_branch') or '当前分支'}」。"
            "填写中文提交说明；默认推送到远程。模型不会执行 git。"
        ),
    }


def confirm(
    job_id: str,
    *,
    message: str = "",
    push: bool | None = None,
    decision: str = "approve",
) -> dict[str, Any]:
    """HITL 确认：approve → commit(+push)；reject → skipped。禁止模型代执行。"""
    cfg = get_config()
    if not cfg.enabled:
        return {"ok": False, "detail": "提交车道未开启", "reply": "提交车道未开启"}

    job = load_job(default_data_dir(), job_id)
    if not job:
        return {"ok": False, "detail": "任务不存在", "reply": "任务不存在"}

    dec = (decision or "approve").strip().lower()
    if dec in {"reject", "cancel", "skip", "no"}:
        update_job(default_data_dir(), job_id, status="skipped")
        return {
            "ok": True,
            "job_id": job_id,
            "status": "skipped",
            "reply": "已取消提交",
            "detail": "用户取消",
        }

    if job.get("status") == "blocked" or not (job.get("gate") or {}).get("can_commit", False):
        if job.get("status") == "blocked" or not cfg.allow_blocked:
            return {
                "ok": False,
                "job_id": job_id,
                "status": "blocked",
                "can_commit": False,
                "findings": job.get("findings") or [],
                "detail": "门禁未通过，禁止提交",
                "reply": "存在阻断项，请先修复后再提交",
            }

    if job.get("status") == "done":
        return {
            "ok": True,
            "job_id": job_id,
            "status": "done",
            "commit_result": job.get("commit_result"),
            "reply": "该任务已提交过",
            "detail": "already done",
        }

    if job.get("status") == "committing":
        return {
            "ok": False,
            "job_id": job_id,
            "status": "committing",
            "detail": "提交进行中，请勿重复确认",
            "reply": "提交进行中，请勿重复确认",
        }

    if job.get("status") != "awaiting_commit":
        return {
            "ok": False,
            "job_id": job_id,
            "status": job.get("status"),
            "detail": f"任务状态不可确认：{job.get('status')}",
            "reply": f"任务状态不可确认：{job.get('status')}",
        }

    msg = (message or "").strip() or str(job.get("draft_message") or "").strip()
    ok_msg, err_msg = validate_chinese_commit_message(msg)
    if not ok_msg:
        return {"ok": False, "detail": err_msg, "reply": err_msg, "job_id": job_id}

    do_push = cfg.default_push if push is None else bool(push)
    work_branch = str(
        job.get("work_branch")
        or resolve_work_branch(workspace=job.get("workspace"), work_branch=cfg.work_branch)
    )
    ok_br, err_br = validate_branch_name(work_branch)
    if not ok_br:
        return {"ok": False, "detail": err_br, "reply": err_br, "job_id": job_id}

    files = list(job.get("files") or [])
    # 确认前重跑本地硬规则（防门禁后改文件内容）
    re_gate = run_commit_review_gate(
        job["workspace"],
        files,
        allow_blocked_override=cfg.allow_blocked,
        use_skill_review=False,
    )
    if not re_gate.get("can_commit") and not cfg.allow_blocked:
        update_job(
            default_data_dir(),
            job_id,
            status="blocked",
            gate={
                **(job.get("gate") or {}),
                "can_commit": False,
                "summary": re_gate.get("summary"),
                "verdict": "blocked",
                "blocking_count": re_gate.get("blocking_count"),
                "review_method": "confirm 重检：" + str(re_gate.get("review_method") or ""),
            },
            findings=re_gate.get("findings") or [],
        )
        return {
            "ok": False,
            "job_id": job_id,
            "status": "blocked",
            "can_commit": False,
            "findings": re_gate.get("findings") or [],
            "detail": "确认前复检未通过",
            "reply": (re_gate.get("summary") or "确认前复检发现阻断项，禁止提交。请修复后重新门禁。"),
        }

    claimed = claim_job_for_commit(default_data_dir(), job_id)
    if not claimed:
        return {
            "ok": False,
            "job_id": job_id,
            "detail": "无法锁定任务（可能已被确认或已过期）",
            "reply": "无法锁定任务，请重新发起门禁审核",
        }

    result = commit_synced_files(
        job["workspace"],
        files,
        message=msg,
        work_branch=work_branch,
        push=do_push,
    )

    push_info = result.get("push") if isinstance(result.get("push"), dict) else None
    push_ok = (not do_push) or (push_info is not None and bool(push_info.get("ok")))
    overall_ok = bool(result.get("ok")) and push_ok

    if result.get("ok"):
        update_job(
            default_data_dir(),
            job_id,
            status="done",
            commit_result=result,
            message=msg,
            push=do_push,
        )
        reply = f"已提交到分支 `{result.get('branch')}`"
        if result.get("commit"):
            reply += f"（{result.get('commit')}）"
        if do_push:
            if push_info and push_info.get("ok"):
                reply += "，并已推送到远程。"
            elif push_info:
                reply += f"。本地已提交，但推送失败：{push_info.get('error') or ''}。"
                reply += push_retry_hint(str(push_info.get("raw_error") or push_info.get("error") or ""))
            else:
                reply += "。"
        else:
            reply += "（未推送）。"
        return {
            "ok": overall_ok,
            "job_id": job_id,
            "status": "done",
            "workspace": str(job.get("workspace") or ""),
            "message": msg,
            "files": list(files),
            "commit_result": result,
            "reply": reply,
            "detail": reply,
            "push_retry_needed": is_push_retry_needed(result),
        }

    update_job(default_data_dir(), job_id, status="awaiting_commit", commit_result=result)
    return {
        "ok": False,
        "job_id": job_id,
        "status": "awaiting_commit",
        "commit_result": result,
        "detail": result.get("error") or "提交失败",
        "reply": result.get("error") or "提交失败",
        "push_retry_needed": is_push_retry_needed(result),
    }


def push_retry(job_id: str) -> dict[str, Any]:
    """本地已 commit、仅重试 push（不重新 commit）。"""
    cfg = get_config()
    if not cfg.enabled:
        return {"ok": False, "detail": "提交车道未开启", "reply": "提交车道未开启"}

    job = load_job(default_data_dir(), job_id)
    if not job:
        return {"ok": False, "detail": "任务不存在", "reply": "任务不存在"}

    prev = job.get("commit_result") if isinstance(job.get("commit_result"), dict) else {}
    if not is_push_retry_needed(prev) and not str(prev.get("commit") or "").strip():
        return {
            "ok": False,
            "detail": "无需重试推送（尚未完成本地 commit）",
            "reply": "无需重试推送",
        }

    root = Path(job["workspace"])
    branch = str(
        job.get("work_branch")
        or prev.get("branch")
        or resolve_work_branch(workspace=root, work_branch=cfg.work_branch)
    )
    push_out = _push_work_branch(root, branch)
    new_result = {
        **prev,
        "push": push_out,
        "ok": True if push_out.get("ok") else prev.get("ok", True),
        "branch": prev.get("branch") or branch,
    }
    update_job(default_data_dir(), job_id, commit_result=new_result, status="done")
    files = list(prev.get("files") or job.get("files") or [])
    msg = str(job.get("message") or prev.get("message") or "").strip()
    workspace = str(job.get("workspace") or "")
    if push_out.get("ok"):
        sha = str(new_result.get("commit") or "").strip()
        reply = f"已提交到分支 `{branch}`"
        if sha:
            reply += f"（{sha}）"
        reply += "，并已推送到远程。"
        return {
            "ok": True,
            "job_id": job_id,
            "status": "done",
            "workspace": workspace,
            "message": msg,
            "files": files,
            "push": push_out,
            "commit_result": new_result,
            "reply": reply,
            "detail": reply,
        }
    return {
        "ok": False,
        "job_id": job_id,
        "workspace": workspace,
        "message": msg,
        "files": files,
        "push": push_out,
        "commit_result": new_result,
        "detail": push_out.get("error") or "推送失败",
        "reply": push_out.get("error") or "推送失败",
        "hint": push_retry_hint(str(push_out.get("raw_error") or push_out.get("error") or "")),
        "push_retry_needed": True,
    }


def get_job(job_id: str) -> dict[str, Any]:
    row = load_job(default_data_dir(), job_id)
    if not row:
        return {"ok": False, "detail": "任务不存在", "reply": "任务不存在"}
    return {"ok": True, "job": row, "reply": row.get("status") or "", "detail": job_id}


def latest_blocked(*, workspace: str = "", job_id: str = "") -> dict[str, Any]:
    """查询最近一次阻断的提交门禁任务（供「修复这些问题」闭环）。"""
    row = latest_blocked_job(default_data_dir(), workspace=workspace, job_id=job_id)
    if not row:
        return {
            "ok": False,
            "detail": "没有找到阻断中的提交门禁任务",
            "reply": (
                "没有找到最近的提交阻断记录。请先说「提交代码」跑门禁；"
                "若已阻断，可再说「修复这些问题」。"
            ),
        }
    findings = list(row.get("findings") or [])
    blocking = [
        f
        for f in findings
        if isinstance(f, dict)
        and (
            f.get("blocking")
            or str(f.get("severity") or "").upper() in {"P0", "P1"}
        )
    ]
    paths = _unique_finding_paths(blocking or findings)
    return {
        "ok": True,
        "job": row,
        "job_id": row.get("id"),
        "workspace": row.get("workspace"),
        "work_branch": row.get("work_branch") or "",
        "findings": findings,
        "blocking_count": len(blocking),
        "fix_paths": paths,
        "reply": (
            f"最近阻断任务 {row.get('id')}：{len(blocking)} 条阻断，"
            f"涉及 {len(paths)} 个文件路径"
        ),
        "detail": row.get("id"),
    }


def _unique_finding_paths(findings: list[Any], *, limit: int = 40) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for f in findings:
        if not isinstance(f, dict):
            continue
        rel = str(f.get("path") or "").replace("\\", "/").strip().lstrip("./")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        out.append(rel)
        if len(out) >= limit:
            break
    return out


def build_fix_requirement(job: dict[str, Any]) -> tuple[str, list[str], str]:
    """从阻断 Job 生成写码需求 + write_scope 路径。返回 (requirement, paths, goal)。"""
    findings = [f for f in (job.get("findings") or []) if isinstance(f, dict)]
    blocking = [
        f
        for f in findings
        if f.get("blocking") or str(f.get("severity") or "").upper() in {"P0", "P1"}
    ]
    focus = blocking or findings
    paths = _unique_finding_paths(focus)
    jid = str(job.get("id") or "")
    ws = str(job.get("workspace") or "")
    lines = [
        f"【门禁阻断修复】请根据提交门禁批审结果修复问题代码（来源任务 {jid}）。",
        f"工程：{ws}",
        f"工作分支（修复后仍提交到此分支）：{job.get('work_branch') or '（沿用仓库/配置）'}",
        "",
        "【须修复的问题】",
    ]
    for f in focus[:20]:
        sev = str(f.get("severity") or "?").upper()
        p = str(f.get("path") or "?")
        msg = str(f.get("message") or "").strip()
        rule = str(f.get("rule") or "").strip()
        extra = f"（规则 {rule}）" if rule else ""
        lines.append(f"- [{sev}] {p}: {msg}{extra}")
    if paths:
        lines.append("")
        lines.append("【优先改动文件】")
        for p in paths[:24]:
            lines.append(f"  - {p}")
    lines.extend(
        [
            "",
            "【硬性约束】",
            "1) 只修复上述阻断/警告相关问题，勿扩大改动范围；",
            "2) 消除 eval / 敏感路径 / 硬编码密钥等门禁命中项；",
            "3) 不要执行 git commit / push；修复完成后由用户再说「提交代码」走门禁确认。",
            "【验收】重新门禁后 P0/P1 应清零或可合理解释。",
        ]
    )
    goal = (
        f"按提交门禁 {jid} 修复 {len(focus)} 个问题"
        + (f"（{', '.join(paths[:3])}{'…' if len(paths) > 3 else ''}）" if paths else "")
    )
    return "\n".join(lines), paths, goal


def prepare_fix_from_gate(
    *,
    workspace: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """把最近阻断门禁转成写码确认卡数据（不自动 start）。"""
    from .. import plugins_store
    from ..code_dev.config import availability as code_dev_availability
    from ..code_dev.ops import FEATURE_ID as CODE_DEV_FEATURE

    blocked_feat = plugins_store.require_enabled(CODE_DEV_FEATURE, capability="本机 Cursor 写码")
    if blocked_feat:
        return {
            **blocked_feat,
            "reply": blocked_feat.get("detail")
            or "写码功能未启用：请到「功能插件」启用 code-dev 后再修复。",
        }

    avail = code_dev_availability()
    if not avail.get("ok"):
        return {
            "ok": False,
            "detail": avail.get("detail") or "写码车道未就绪",
            "reply": (
                "已识别为**按门禁修复**，但本机写码尚未就绪：\n\n"
                f"• {avail.get('detail') or '未就绪'}\n\n"
                "请到引擎配置中心开启写码车道并配置 Cursor API Key。"
            ),
        }

    looked = latest_blocked(workspace=workspace, job_id=job_id)
    if not looked.get("ok"):
        return looked

    job = looked["job"]
    req, paths, goal = build_fix_requirement(job)
    ws = str(job.get("workspace") or workspace or "").strip()
    brief = {
        "original_goal": goal,
        "workspace": ws,
        "selections": [
            {
                "round": 1,
                "lines": [
                    f"工程路径：{ws}",
                    f"来源：提交门禁阻断 {job.get('id')}",
                    f"优先文件：{', '.join(paths[:8])}" if paths else "优先文件：（见需求正文）",
                ],
            }
        ],
        "notes": [
            f"source=code_commit_gate",
            f"gate_job_id={job.get('id')}",
            f"work_branch={job.get('work_branch') or ''}",
        ],
        "option_rounds": 1,
    }
    ui = {
        "kind": "propose",
        "workspace": ws,
        "requirement": req,
        "target": "local",
        "propose": {
            "target": "local",
            "workspace": ws,
            "requirement": req,
            "original_goal": goal,
            "expected_paths": paths[:12],
            "target_module": "提交门禁修复",
        },
        "brief": brief,
        "original_goal": goal,
        "target_hints": {
            "module": "提交门禁修复",
            "confidence": "high",
            "expected_paths": paths[:12],
            "keywords": ["门禁", "修复"],
        },
        "write_scope": paths[:40],
        "source_gate_job_id": job.get("id"),
        "work_branch": job.get("work_branch") or "",
        "validation": {
            "ok": True,
            "errors": [],
            "warnings": [
                "本需求来自提交门禁阻断；请核对文件与问题列表后再用 Cursor 写入本机。"
                "修复完成后请再说「提交代码」重新门禁。"
            ],
        },
        "hint": "门禁修复 · 确认后写码",
        "summary": "按提交门禁结果修复问题代码",
        "desc": f"工程 {ws} · 任务 {job.get('id')} · {len(paths)} 个优先文件",
    }
    return {
        "ok": True,
        "job_id": job.get("id"),
        "workspace": ws,
        "work_branch": job.get("work_branch") or "",
        "fix_paths": paths,
        "findings": job.get("findings") or [],
        "code_dev_ui": ui,
        "code_dev_brief": brief,
        "source": "code_commit_fix",
        "data_source": "code_commit",
        "intent": {
            "type": "code_dev",
            "metric": "propose",
            "dim": "gate_fix",
            "chart": None,
        },
        "thinking": "已定位最近一次提交门禁阻断，整理为写码确认卡（不自动开工）。",
        "reply": (
            "已根据**最近一次提交门禁阻断**整理修复确认卡。\n\n"
            f"• 工程：`{ws}`\n"
            f"• 门禁任务：`{job.get('id')}`\n"
            f"• 优先文件：{len(paths)} 个\n\n"
            "请核对下方确认卡后点确认，才会启动 Cursor 写码。"
            "修好后再说「提交代码」重新门禁并确认提交。"
        ),
        "detail": f"gate={job.get('id')}",
        "note": "gate_fix_propose",
    }
