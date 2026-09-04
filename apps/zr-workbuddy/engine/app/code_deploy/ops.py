"""部署车道：prepare（算单元）→ confirm（人确认后 SSH 同步）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import availability, get_config, validate_ssh_settings
from .diff_map import resolve_units_from_ids, units_from_diff
from .ssh_sync import deploy_units_ssh
from .store import (
    claim_job,
    get_last_deploy_record,
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


def _enrich_unit_for_ui(u: dict[str, Any], cfg: Any) -> dict[str, Any]:
    """按真实配置改写 action_hint，避免卡片写「重启 DSH」但实际不会执行。"""
    row = dict(u)
    uid = str(row.get("id") or "")
    action = str(row.get("action") or "")
    if uid == "bridge" or action in {"sync_bridge", "sync_bridge_reinstall"}:
        if getattr(cfg, "auto_restart_bridge", True):
            row["action"] = "sync_bridge_reinstall"
            row["action_hint"] = "同步 bridge 后重装并重启远端 DSH（面板 UI 立即生效）"
            row["risk"] = "high"
        else:
            row["action"] = "sync_bridge"
            row["action_hint"] = (
                "仅同步 bridge 文件，不重启 DSH（auto_restart_bridge=false）；"
                "面板 UI 需另行重启远端 DSH 才生效"
            )
            row["risk"] = "medium"
    elif uid == "engine" or action == "sync_engine_restart":
        if getattr(cfg, "auto_restart_engine", True):
            row["action_hint"] = "同步引擎代码后重启本应用引擎（不影响其它服务）"
        else:
            row["action_hint"] = "同步引擎文件；按配置跳过远端引擎重启"
    return row


def _enrich_units(units: list[dict[str, Any]], cfg: Any) -> list[dict[str, Any]]:
    return [_enrich_unit_for_ui(u, cfg) for u in units if isinstance(u, dict)]


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

    last_rec = get_last_deploy_record(default_data_dir(), target_env)
    last_sha = str(last_rec.get("sha") or "").strip()
    known_dirty_fps = dict(last_rec.get("dirty_fingerprints") or {})
    first_deploy = not bool(last_sha)
    head = (head_ref or "").strip() or cfg.default_ref or "HEAD"
    # 基线：显式 base > 上次成功 SHA；无记录时不做「假增量」对比
    base = (base_ref or "").strip() or last_sha or ""

    catalog_objs = list_catalog_units(root)
    units_full = _enrich_units([u.to_dict() for u in catalog_objs], cfg)

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
            "dirty_skipped_same_as_last": [],
            "unit_objs": [],
            "units": [],
            "skipped_paths": [],
            "base_ref": "(none)",
            "base_sha": "",
            "head_ref": head,
            "head_sha": "",
            "base_resolved": False,
        }
        from .diff_map import filter_unchanged_dirty_paths, list_changed_paths, list_dirty_paths
        from .units import map_paths_to_units

        tip = list_changed_paths(root, base_ref="HEAD", head_ref="HEAD")
        if tip.get("ok"):
            mapped["head_ref"] = tip.get("head_ref") or head
            mapped["head_sha"] = tip.get("head_sha") or ""
            dirty = list_dirty_paths(root)
            raw_dirty = list(dirty.get("paths") or []) if dirty.get("ok") else []
            dirty_paths, dirty_skipped = filter_unchanged_dirty_paths(
                root, raw_dirty, known_dirty_fps
            )
            mapped["dirty_paths"] = dirty_paths
            mapped["dirty_skipped_same_as_last"] = dirty_skipped
            mapped["paths"] = list(dirty_paths)
            mapped["unit_objs"] = map_paths_to_units(dirty_paths)
            mapped["units"] = [u.to_dict() for u in mapped["unit_objs"]]
        base_resolved = False
    else:
        mapped = units_from_diff(
            root,
            base_ref=base,
            head_ref=head,
            include_dirty=True,
            known_dirty_fingerprints=known_dirty_fps,
        )
        if not mapped.get("ok"):
            base_resolved = False
            from .diff_map import filter_unchanged_dirty_paths, list_changed_paths, list_dirty_paths
            from .units import map_paths_to_units

            tip = list_changed_paths(root, base_ref="HEAD", head_ref=head)
            dirty = list_dirty_paths(root)
            raw_dirty = list(dirty.get("paths") or []) if dirty.get("ok") else []
            dirty_paths, dirty_skipped = filter_unchanged_dirty_paths(
                root, raw_dirty, known_dirty_fps
            )
            mapped = {
                "ok": True,
                "paths": dirty_paths,
                "dirty_paths": dirty_paths,
                "dirty_skipped_same_as_last": dirty_skipped,
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
    # mode=auto 走策略；显式 mode 仅允许增量→全量升级（强制全量不可降级）
    decision = apply_user_mode_override(decision, mode if mode != "auto" else "")
    deploy_mode = decision.mode
    if decision.force_full:
        deploy_mode = "full"

    units_incremental = _enrich_units([u.to_dict() for u in incr_objs], cfg)
    from .policy import resolve_execution_plan

    execution = resolve_execution_plan(
        mode=deploy_mode,
        force_full=decision.force_full,
        units_full=units_full,
        units_incremental=units_incremental,
    )
    active_objs = catalog_objs if deploy_mode == "full" else incr_objs
    units = _enrich_units([u.to_dict() for u in active_objs], cfg)

    avail = availability()
    can_deploy = bool(avail.get("ok")) and (
        bool(execution.get("unit_ids")) if deploy_mode == "full" else True
    )
    # 增量且无单元：仍允许出卡，但 can_deploy=false（除非升级全量）
    if deploy_mode == "incremental" and not execution.get("unit_ids"):
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
        "recommend_full": False,
        "allow_mode_override": decision.allow_upgrade_to_full,
        "allow_upgrade_to_full": decision.allow_upgrade_to_full,
        "policy": policy,
        "execution": execution,
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
        "dirty_skipped_same_as_last": mapped.get("dirty_skipped_same_as_last") or [],
        "skipped_paths": mapped.get("skipped_paths") or [],
        "ssh_host": cfg.ssh_host,
        "ssh_app_path": cfg.ssh_app_path,
        "health_url": (cfg.health_url or "").strip(),
        "provider": cfg.provider,
        "can_deploy": can_deploy,
        "gate_detail": avail.get("detail") or "",
        "remote_empty": remote_empty,
    }
    save_job(default_data_dir(), job)

    reason_txt = "；".join(decision.reasons[:3]) if decision.reasons else ""
    if deploy_mode == "full":
        if decision.force_full:
            reply = (
                f"策略判定 **全量部署**（已锁定，不可改增量）→ **{target_env}**"
                f"（`{cfg.ssh_host}`），**{len(units_full)}** 个单元。"
            )
        else:
            reply = (
                f"将执行 **全量部署** → **{target_env}**（`{cfg.ssh_host}`），"
                f"**{len(units_full)}** 个单元。"
            )
        if reason_txt:
            reply += f"\n原因：{reason_txt}"
        reply += "\n人只须确认触发；未确认不会 rsync。"
    elif not units_incremental:
        reply = (
            f"相对上次部署无业务单元变更（`{job['base_ref']}` → `{job['head_ref']}`）。"
            "确认将不执行同步；若远端异常可升级为全量。"
        )
    else:
        labels = "、".join(u["id"] for u in units_incremental)
        reply = (
            f"策略判定 **增量部署** → **{target_env}**：自动全选 **{labels}**。"
            + (f"\n原因：{reason_txt}" if reason_txt else "")
            + "\n人只须确认触发；未确认不会 rsync。需要时可将本任务升级为全量。"
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
        "recommend_full": False,
        "execution": execution,
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
    allow_upgrade = (not force_full) and bool(
        job.get("allow_upgrade_to_full", job.get("allow_mode_override"))
    )
    units_full = job.get("units_full") or []
    units_incr = job.get("units_incremental") or []
    units = units_full if mode == "full" else units_incr
    policy = job.get("policy") or {}
    reasons = policy.get("reasons") or job.get("reasons") or []
    warnings = policy.get("warnings") or []
    execution = job.get("execution") or {}
    badge = "全量部署" if mode == "full" else "增量部署"
    if force_full:
        badge = "强制全量"
    return {
        "kind": "confirm",
        "status": "pending",
        "job_id": job.get("id"),
        "workspace": job.get("workspace") or "",
        "env": job.get("env") or "",
        "mode": mode,
        "force_full": force_full,
        "recommend_full": False,
        "allow_mode_override": allow_upgrade,
        "allow_upgrade_to_full": allow_upgrade,
        "locked_mode": "full" if force_full else "",
        "execution": execution,
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
        "health_url": job.get("health_url") or "",
        "access_url": job.get("health_url") or "",
        "can_deploy": bool(job.get("can_deploy")),
        "hint": (
            "已判定全量：确认后同步全部单元，不可改增量"
            if force_full
            else "已判定增量：确认后只同步命中单元；需要时可升级为全量"
        ),
        "summary": f"{badge} · {job.get('env')}",
        "desc": (
            "二元策略：触发全量条件则全量锁定；否则增量。"
            "对比上次成功部署 SHA → HEAD（含未提交，已部署同内容脏文件会忽略）。"
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

    from .policy import resolve_confirm_mode, resolve_execution_plan

    deploy_mode, mode_err = resolve_confirm_mode(
        job_mode=str(job.get("mode") or "incremental"),
        force_full=bool(job.get("force_full")),
        requested_mode=mode,
    )
    if mode_err:
        return {
            "ok": False,
            "detail": mode_err,
            "reply": mode_err,
            "job_id": job_id,
            "force_full": True,
        }

    # 执行集以策略计划为准：全量=目录全部单元；增量=prepare 命中单元（忽略客户端随意瘦身）
    plan = resolve_execution_plan(
        mode=deploy_mode,
        force_full=bool(job.get("force_full")) and deploy_mode == "full",
        units_full=job.get("units_full") or [],
        units_incremental=job.get("units_incremental") or [],
    )
    unit_ids = list(plan.get("unit_ids") or [])
    if deploy_mode == "incremental" and unit_ids is not None and unit_ids == []:
        # 无增量单元：允许「空确认」视为成功跳过，或升级全量；此处拒绝空同步
        return {
            "ok": False,
            "detail": "当前无增量单元可同步；请升级为全量或取消",
            "reply": "当前无增量单元可同步；请升级为全量或取消",
            "job_id": job_id,
        }

    raw_units = (
        (job.get("units_full") or [])
        if deploy_mode == "full"
        else (job.get("units_incremental") or [])
    )
    unit_objs = []
    for u in raw_units:
        if isinstance(u, dict) and u.get("id"):
            built = resolve_units_from_ids([u["id"]])
            if built:
                unit_objs.append(built[0])
    selected = filter_units_by_ids(unit_objs, unit_ids)
    if not selected:
        return {
            "ok": False,
            "detail": "未选择部署单元",
            "reply": "请升级为全量部署，或取消后重试",
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

    result = deploy_units_ssh(
        job["workspace"],
        selected,
        cfg,
        log=_log,
        meta={
            "job_id": job_id,
            "mode": deploy_mode,
            "env": job.get("env") or cfg.default_env,
            "head_sha": str(job.get("head_sha") or ""),
            "workspace": str(job.get("workspace") or ""),
        },
    )
    mode_label = "全量" if deploy_mode == "full" else "增量"
    if result.get("ok"):
        # 成功时刻重读 HEAD + 脏文件指纹，避免同内容未提交文件下次再锁全量
        from .diff_map import fingerprint_paths, list_changed_paths, list_dirty_paths

        ws = Path(str(job.get("workspace") or ".")).expanduser()
        tip = list_changed_paths(ws, base_ref="HEAD", head_ref="HEAD")
        sha = str(
            (tip.get("head_sha") if tip.get("ok") else "") or job.get("head_sha") or ""
        ).strip()
        dirty_now = list_dirty_paths(ws)
        dirty_list = list(dirty_now.get("paths") or []) if dirty_now.get("ok") else []
        fps = fingerprint_paths(ws, dirty_list)
        if deploy_mode != "full":
            prev = get_last_deploy_record(
                default_data_dir(), str(job.get("env") or cfg.default_env)
            )
            merged = dict(prev.get("dirty_fingerprints") or {})
            merged.update(fps)
            fps = merged
        if sha:
            set_last_deploy_sha(
                default_data_dir(),
                str(job.get("env") or cfg.default_env),
                sha,
                dirty_fingerprints=fps,
            )
        update_job(
            default_data_dir(),
            job_id,
            status="done",
            deploy_result=result,
            logs=logs[-80:],
        )
        unit_ids = [u.id for u in selected]
        access = (cfg.health_url or "").strip() or str(job.get("health_url") or "").strip()
        remote = f"{cfg.ssh_host}:{cfg.ssh_app_path}"
        engine_port = result.get("remote_engine_port")
        health = result.get("health") or {}
        actions: list[str] = []
        if result.get("engine_restart"):
            actions.append("已重启引擎" + (f"（:{engine_port}）" if engine_port else ""))
        if result.get("bridge_restart"):
            actions.append("已重装 bridge 并后台重启远端 DSH")
        if not actions:
            actions.append("仅同步文件")
        # 人只触发：含 bridge 且已重启时，成功摘要点明面板已收尾
        if result.get("bridge_restart"):
            reply_extra = "\n- 面板：远端 DSH 已后台重启（bridge 变更已收尾）"
        elif "bridge" in unit_ids and not getattr(cfg, "auto_restart_bridge", True):
            reply_extra = "\n- 面板：未重启 DSH（auto_restart_bridge=false）"
        else:
            reply_extra = ""
        title = f"{mode_label}部署完成"
        receipt_path = str(result.get("remote_receipt_path") or "").strip()
        synced_rels = []
        for u in selected:
            synced_rels.extend(list(u.local_rels))
        # 去重保序
        _seen_rel: set[str] = set()
        synced_unique: list[str] = []
        for r in synced_rels:
            if r not in _seen_rel:
                _seen_rel.add(r)
                synced_unique.append(r)
        synced_rels = synced_unique
        head_sha = sha or str(job.get("head_sha") or "").strip()
        unit_short = "、".join(unit_ids[:4]) + ("…" if len(unit_ids) > 4 else "")
        health_ok = isinstance(health, dict) and bool(health.get("ok"))
        health_bit = "探活通过" if health_ok else (
            "探活未通过" if isinstance(health, dict) and health.get("ok") is False else "探活未配置"
        )
        reply = (
            f"**{title}** · `{unit_short or '—'}`\n"
            f"- 环境：`{job.get('env') or cfg.default_env}` · {health_bit}\n"
            f"- 远端：`{remote}`"
            f"{reply_extra}"
        )
        success = {
            "title": title,
            "mode": deploy_mode,
            "mode_label": mode_label,
            "env": job.get("env") or cfg.default_env,
            "ssh_host": cfg.ssh_host,
            "ssh_app_path": cfg.ssh_app_path,
            "remote": remote,
            "access_url": access,
            "health_url": access,
            "units": unit_ids,
            "synced_rels": synced_rels,
            "engine_restart": bool(result.get("engine_restart")),
            "bridge_restart": bool(result.get("bridge_restart")),
            "remote_engine_port": engine_port,
            "head_sha": head_sha,
            "actions": actions,
            "health": health if isinstance(health, dict) else None,
            "remote_receipt_path": receipt_path,
            "remote_receipt_ok": bool(result.get("remote_receipt_ok")),
        }
        return {
            "ok": True,
            "job_id": job_id,
            "status": "done",
            "mode": deploy_mode,
            "deploy_result": result,
            "deploy_success": success,
            "code_deploy_ui": {
                "kind": "success",
                **success,
            },
            "units": unit_ids,
            "access_url": access,
            "health_url": access,
            "ssh_host": cfg.ssh_host,
            "ssh_app_path": cfg.ssh_app_path,
            "env": success["env"],
            "head_sha": head_sha,
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
