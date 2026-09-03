"""部署车道：prepare（算单元）→ confirm（人确认后 SSH 同步）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import availability, get_config, validate_ssh_settings
from .diff_map import resolve_units_from_ids, units_from_diff
from .ssh_sync import deploy_units_ssh
from .store import (
    claim_job,
    get_last_deploy_sha,
    load_job,
    new_job_id,
    save_job,
    set_last_deploy_sha,
    update_job,
)
from .units import filter_units_by_ids, list_catalog_units

FEATURE_ID = "code-deploy"


def default_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def status() -> dict[str, Any]:
    avail = availability()
    cfg = get_config()
    last = {}
    for env in cfg.env_whitelist or ["staging"]:
        sha = get_last_deploy_sha(default_data_dir(), env)
        if sha:
            last[env] = sha
    return {
        "ok": bool(avail.get("ok")),
        "feature": FEATURE_ID,
        "code_deploy": avail,
        "reply": avail.get("detail") or "",
        "detail": avail.get("detail") or "",
        "env_whitelist": list(cfg.env_whitelist),
        "default_env": cfg.default_env,
        "provider": cfg.provider,
        "last_deploy_sha": last,
        "first_deploy": not bool(last.get(cfg.default_env or "staging")),
    }


def _normalize_mode(mode: str, *, first_deploy: bool) -> str:
    m = (mode or "").strip().lower()
    if m in {"full", "all", "全量"}:
        return "full"
    if m in {"incremental", "incr", "diff", "增量"}:
        return "incremental"
    return "full" if first_deploy else "incremental"


def prepare(
    workspace: str = "",
    *,
    env: str = "",
    base_ref: str = "",
    head_ref: str = "HEAD",
    unit_ids: list[str] | None = None,
    mode: str = "auto",
) -> dict[str, Any]:
    """对比上次成功部署 SHA → 策略判定全量/增量；人只确认触发。"""
    from .policy import apply_user_mode_override, decide_deploy_mode
    from .ssh_sync import probe_remote_app

    cfg = get_config()
    if not cfg.enabled:
        return {
            "ok": False,
            "detail": "部署车道未开启",
            "reply": availability().get("detail") or "部署车道未开启",
            "can_deploy": False,
        }
    root = Path((workspace or cfg.default_workspace or "").strip() or ".").expanduser()
    try:
        root = root.resolve()
    except OSError:
        return {"ok": False, "detail": "工作区路径无效", "reply": "工作区路径无效", "can_deploy": False}
    if not root.is_dir():
        return {"ok": False, "detail": "目录不存在", "reply": "目录不存在", "can_deploy": False}
    if not (root / ".git").exists():
        # 允许 worktree：用 git 探测
        from .diff_map import list_changed_paths

        tip = list_changed_paths(root, base_ref="HEAD", head_ref="HEAD")
        if not tip.get("ok"):
            return {
                "ok": False,
                "detail": "工作区不是 git 仓库",
                "reply": tip.get("error") or "工作区不是 git 仓库",
                "can_deploy": False,
            }

    target_env = (env or cfg.default_env or "staging").strip().lower()
    if target_env not in cfg.env_whitelist:
        return {
            "ok": False,
            "detail": f"环境「{target_env}」不在白名单 {cfg.env_whitelist}",
            "reply": f"环境「{target_env}」不允许部署",
            "can_deploy": False,
        }

    last_sha = get_last_deploy_sha(default_data_dir(), target_env)
    first_deploy = not bool(last_sha)
    head = (head_ref or "").strip() or cfg.default_ref or "HEAD"
    # 基线：显式 base > 上次成功 SHA；无记录时不做「假增量」对比
    base = (base_ref or "").strip() or last_sha or ""

    catalog_objs = list_catalog_units(root)
    units_full = [u.to_dict() for u in catalog_objs]

    remote_empty = None
    remote_probe_error = ""
    if not validate_ssh_settings(cfg):
        probe = probe_remote_app(cfg)
        if probe.get("ok"):
            remote_empty = bool(probe.get("empty"))
        else:
            remote_probe_error = str(probe.get("error") or "探测失败")

    base_resolved = True
    mapped: dict[str, Any]
    if not base:
        mapped = {
            "ok": True,
            "paths": [],
            "dirty_paths": [],
            "unit_objs": [],
            "units": [],
            "skipped_paths": [],
            "base_ref": "(none)",
            "base_sha": "",
            "head_ref": head,
            "head_sha": "",
            "base_resolved": False,
        }
        # 仍解析 HEAD sha 供成功后落盘
        from .diff_map import list_changed_paths

        tip = list_changed_paths(root, base_ref="HEAD", head_ref="HEAD")
        if tip.get("ok"):
            mapped["head_ref"] = tip.get("head_ref") or head
            mapped["head_sha"] = tip.get("head_sha") or ""
            # 拉 dirty 以便策略提示
            from .diff_map import list_dirty_paths
            from .units import map_paths_to_units

            dirty = list_dirty_paths(root)
            dirty_paths = list(dirty.get("paths") or []) if dirty.get("ok") else []
            mapped["dirty_paths"] = dirty_paths
            mapped["paths"] = list(dirty_paths)
            mapped["unit_objs"] = map_paths_to_units(dirty_paths)
            mapped["units"] = [u.to_dict() for u in mapped["unit_objs"]]
        base_resolved = False
    else:
        mapped = units_from_diff(root, base_ref=base, head_ref=head, include_dirty=True)
        if not mapped.get("ok"):
            # 基线坏了 → 强制全量路径，仍给确认卡
            base_resolved = False
            from .diff_map import list_changed_paths, list_dirty_paths
            from .units import map_paths_to_units

            tip = list_changed_paths(root, base_ref="HEAD", head_ref=head)
            dirty = list_dirty_paths(root)
            dirty_paths = list(dirty.get("paths") or []) if dirty.get("ok") else []
            mapped = {
                "ok": True,
                "paths": dirty_paths,
                "dirty_paths": dirty_paths,
                "unit_objs": map_paths_to_units(dirty_paths),
                "units": [],
                "skipped_paths": [],
                "base_ref": base,
                "base_sha": "",
                "head_ref": (tip.get("head_ref") if tip.get("ok") else head) or head,
                "head_sha": (tip.get("head_sha") if tip.get("ok") else "") or "",
                "error": mapped.get("error") or "base 解析失败",
            }
            mapped["units"] = [u.to_dict() for u in mapped["unit_objs"]]
        else:
            base_resolved = True

    incr_objs = list(mapped.get("unit_objs") or [])
    if unit_ids is not None:
        forced = resolve_units_from_ids(unit_ids)
        if forced:
            incr_objs = forced
    units_incremental = [u.to_dict() for u in incr_objs]

    decision = decide_deploy_mode(
        last_sha=last_sha,
        base_resolved=base_resolved if last_sha else False,
        paths=list(mapped.get("paths") or []),
        units=incr_objs,
        dirty_paths=list(mapped.get("dirty_paths") or []),
        remote_empty=remote_empty,
        remote_probe_error=remote_probe_error,
    )
    # mode=auto 走策略；显式 mode 尝试覆盖（强制全量时拒绝增量）
    decision = apply_user_mode_override(decision, mode if mode != "auto" else "")
    deploy_mode = decision.mode

    active_objs = catalog_objs if deploy_mode == "full" else incr_objs
    units = [u.to_dict() for u in active_objs]

    avail = availability()
    can_deploy = bool(avail.get("ok")) and (
        bool(units) if deploy_mode == "full" else True
    )
    # 增量且无单元：仍允许出卡，但 can_deploy=false（除非改全量）
    if deploy_mode == "incremental" and not units:
        can_deploy = False

    job_id = new_job_id()
    policy = decision.to_dict()
    job = {
        "id": job_id,
        "feature": FEATURE_ID,
        "status": "awaiting_deploy",
        "workspace": str(root),
        "env": target_env,
        "mode": deploy_mode,
        "force_full": decision.force_full,
        "recommend_full": decision.recommend_full,
        "allow_mode_override": decision.allow_mode_override,
        "policy": policy,
        "first_deploy": decision.first_deploy,
        "last_deploy_sha": last_sha,
        "base_ref": mapped.get("base_ref") or base or "(none)",
        "base_sha": mapped.get("base_sha") or "",
        "head_ref": mapped.get("head_ref") or head,
        "head_sha": mapped.get("head_sha") or "",
        "units": units,
        "units_full": units_full,
        "units_incremental": units_incremental,
        "changed_paths": mapped.get("paths") or [],
        "dirty_paths": mapped.get("dirty_paths") or [],
        "skipped_paths": mapped.get("skipped_paths") or [],
        "ssh_host": cfg.ssh_host,
        "ssh_app_path": cfg.ssh_app_path,
        "provider": cfg.provider,
        "can_deploy": can_deploy,
        "gate_detail": avail.get("detail") or "",
        "remote_empty": remote_empty,
    }
    save_job(default_data_dir(), job)

    reason_txt = "；".join(decision.reasons[:3]) if decision.reasons else ""
    if deploy_mode == "full":
        lock = "（已强制，不可改增量）" if decision.force_full else "（建议全量，可改增量但有风险）"
        reply = (
            f"策略判定 **全量部署**{lock} → **{target_env}**（`{cfg.ssh_host}`），"
            f"**{len(units_full)}** 个单元。"
            + (f"\n原因：{reason_txt}" if reason_txt else "")
            + "\n人只须确认触发；未确认不会 rsync。"
        )
    elif not units_incremental:
        reply = (
            f"相对上次部署无业务单元变更（`{job['base_ref']}` → `{job['head_ref']}`）。"
            "确认将不执行同步；若远端异常请改选全量。"
        )
    else:
        labels = "、".join(u["id"] for u in units_incremental)
        reply = (
            f"策略判定 **增量部署** → **{target_env}**：自动全选 **{labels}**。"
            + (f"\n原因：{reason_txt}" if reason_txt else "")
            + "\n人只须确认触发；未确认不会 rsync。"
        )
    if decision.warnings:
        reply += "\n注意：" + "；".join(decision.warnings[:2])
    if not avail.get("ok"):
        reply += f"\n\nSSH 尚未就绪——{avail.get('detail')}"

    return {
        "ok": True,
        "job_id": job_id,
        "can_deploy": can_deploy,
        "workspace": str(root),
        "env": target_env,
        "mode": deploy_mode,
        "force_full": decision.force_full,
        "recommend_full": decision.recommend_full,
        "policy": policy,
        "first_deploy": decision.first_deploy,
        "last_deploy_sha": last_sha,
        "base_ref": job["base_ref"],
        "base_sha": job["base_sha"],
        "head_ref": job["head_ref"],
        "head_sha": job["head_sha"],
        "units": units,
        "units_full": units_full,
        "units_incremental": units_incremental,
        "changed_paths": job["changed_paths"][:80],
        "dirty_paths": job["dirty_paths"][:40],
        "skipped_paths": job["skipped_paths"],
        "ssh_host": cfg.ssh_host,
        "ssh_app_path": cfg.ssh_app_path,
        "reply": reply,
        "detail": reply,
        "code_deploy_ui": _build_confirm_ui(job),
    }


def _build_confirm_ui(job: dict[str, Any]) -> dict[str, Any]:
    mode = job.get("mode") or "incremental"
    first = bool(job.get("first_deploy"))
    force_full = bool(job.get("force_full"))
    recommend_full = bool(job.get("recommend_full"))
    allow_override = bool(job.get("allow_mode_override"))
    units_full = job.get("units_full") or []
    units_incr = job.get("units_incremental") or []
    units = units_full if mode == "full" else units_incr
    policy = job.get("policy") or {}
    reasons = policy.get("reasons") or []
    warnings = policy.get("warnings") or []
    badge = "强制全量" if force_full else ("建议全量" if recommend_full and mode == "full" else ("全量部署" if mode == "full" else "增量部署"))
    return {
        "kind": "confirm",
        "status": "pending",
        "job_id": job.get("id"),
        "workspace": job.get("workspace") or "",
        "env": job.get("env") or "",
        "mode": mode,
        "force_full": force_full,
        "recommend_full": recommend_full,
        "allow_mode_override": allow_override,
        "first_deploy": first,
        "last_deploy_sha": job.get("last_deploy_sha") or "",
        "base_ref": job.get("base_ref") or "",
        "head_ref": job.get("head_ref") or "",
        "base_sha": job.get("base_sha") or "",
        "head_sha": job.get("head_sha") or "",
        "units": units,
        "units_full": units_full,
        "units_incremental": units_incr,
        "changed_paths": (job.get("changed_paths") or [])[:40],
        "policy": policy,
        "reasons": reasons,
        "warnings": warnings,
        "ssh_host": job.get("ssh_host") or "",
        "ssh_app_path": job.get("ssh_app_path") or "",
        "can_deploy": bool(job.get("can_deploy")),
        "hint": "系统已按上次部署记录自动判定；人只确认触发",
        "summary": f"{badge} · {job.get('env')}",
        "desc": (
            "对比上次成功部署 SHA 与当前 HEAD（含未提交变更）后自动选方式。"
            "强制全量时不可改增量；建议全量时可改，但可能漏发。"
        ),
    }


def confirm(
    job_id: str,
    *,
    decision: str = "approve",
    unit_ids: list[str] | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """HITL：approve → 按模式全量或勾选增量同步；reject → 跳过。"""
    cfg = get_config()
    if not cfg.enabled:
        return {"ok": False, "detail": "部署车道未开启", "reply": "部署车道未开启"}

    job = load_job(default_data_dir(), job_id)
    if not job:
        return {"ok": False, "detail": "任务不存在", "reply": "任务不存在"}

    dec = (decision or "approve").strip().lower()
    if dec in {"reject", "cancel", "skip", "no"}:
        update_job(default_data_dir(), job_id, status="skipped")
        return {"ok": True, "job_id": job_id, "status": "skipped", "reply": "已取消部署"}

    if job.get("status") == "done":
        return {
            "ok": True,
            "job_id": job_id,
            "status": "done",
            "reply": "该任务已部署过",
            "deploy_result": job.get("deploy_result"),
        }
    if job.get("status") == "deploying":
        return {"ok": False, "detail": "部署进行中", "reply": "部署进行中，请勿重复确认"}
    if job.get("status") != "awaiting_deploy":
        return {
            "ok": False,
            "detail": f"状态不可确认：{job.get('status')}",
            "reply": f"状态不可确认：{job.get('status')}",
        }

    avail = availability()
    if not avail.get("ok"):
        return {"ok": False, "detail": avail.get("detail"), "reply": avail.get("detail"), "job_id": job_id}

    # 强制全量：拒绝增量覆盖
    requested = (mode if mode is not None else "") or ""
    if job.get("force_full") and requested.lower() in {"incremental", "incr", "diff", "增量"}:
        return {
            "ok": False,
            "detail": "当前变更必须全量部署，不能改选增量",
            "reply": "当前变更必须全量部署，不能改选增量",
            "job_id": job_id,
            "force_full": True,
        }

    deploy_mode = _normalize_mode(
        mode if mode is not None else (job.get("mode") or "incremental"),
        first_deploy=bool(job.get("first_deploy")),
    )
    if job.get("force_full"):
        deploy_mode = "full"

    if deploy_mode == "full":
        raw_units = job.get("units_full") or job.get("units") or []
        # 全量：默认同步目录全部单元（忽略瘦身勾选，防漏发）
        unit_ids = [u["id"] for u in raw_units if isinstance(u, dict) and u.get("id")]
    else:
        raw_units = job.get("units_incremental") or job.get("units") or []
        # 增量：默认自动全选 diff 单元；若传入 unit_ids 则仍尊重（须为 prepare 集合子集）
        if unit_ids is None:
            unit_ids = [u["id"] for u in raw_units if isinstance(u, dict) and u.get("id")]
        else:
            allowed = {
                str(u.get("id") or "")
                for u in raw_units
                if isinstance(u, dict) and u.get("id")
            }
            unit_ids = [str(x).strip() for x in unit_ids if str(x).strip() in allowed]

    unit_objs = []
    for u in raw_units:
        if isinstance(u, dict) and u.get("id"):
            built = resolve_units_from_ids([u["id"]])
            if built:
                unit_objs.append(built[0])
    selected = filter_units_by_ids(
        unit_objs,
        unit_ids if unit_ids is not None else [u.id for u in unit_objs],
    )
    if not selected:
        return {
            "ok": False,
            "detail": "未选择部署单元",
            "reply": "请至少勾选一个插件/单元，或改选全量部署",
            "job_id": job_id,
        }

    claimed = claim_job(
        default_data_dir(),
        job_id,
        expect_status="awaiting_deploy",
        status="deploying",
        mode=deploy_mode,
        selected_units=[u.id for u in selected],
    )
    if not claimed:
        cur = load_job(default_data_dir(), job_id) or {}
        st = cur.get("status") or "?"
        return {
            "ok": False,
            "detail": f"无法抢占任务（当前状态：{st}）",
            "reply": "部署已在进行或已结束，请勿重复确认",
            "job_id": job_id,
        }
    logs: list[str] = []

    def _log(msg: str) -> None:
        logs.append(msg)

    result = deploy_units_ssh(job["workspace"], selected, cfg, log=_log)
    mode_label = "全量" if deploy_mode == "full" else "增量"
    if result.get("ok"):
        sha = str(job.get("head_sha") or "").strip()
        if sha:
            set_last_deploy_sha(default_data_dir(), str(job.get("env") or cfg.default_env), sha)
        update_job(
            default_data_dir(),
            job_id,
            status="done",
            deploy_result=result,
            logs=logs[-80:],
        )
        ids = "、".join(u.id for u in selected)
        reply = f"已{mode_label}部署：**{ids}** → `{cfg.ssh_host}:{cfg.ssh_app_path}`"
        if result.get("engine_restart"):
            reply += "；已重启引擎"
        if result.get("bridge_restart"):
            reply += "；已重装 bridge"
        return {
            "ok": True,
            "job_id": job_id,
            "status": "done",
            "mode": deploy_mode,
            "deploy_result": result,
            "units": [u.id for u in selected],
            "reply": reply,
            "detail": reply,
            "logs": logs[-40:],
        }

    update_job(
        default_data_dir(),
        job_id,
        status="failed",
        deploy_result=result,
        logs=logs[-80:],
    )
    return {
        "ok": False,
        "job_id": job_id,
        "status": "failed",
        "mode": deploy_mode,
        "deploy_result": result,
        "detail": result.get("error") or "部署失败",
        "reply": result.get("error") or "部署失败",
        "logs": logs[-40:],
    }


def get_job(job_id: str) -> dict[str, Any]:
    row = load_job(default_data_dir(), job_id)
    if not row:
        return {"ok": False, "detail": "任务不存在", "reply": "任务不存在"}
    return {"ok": True, "job": row, "reply": row.get("status") or "", "detail": job_id}
