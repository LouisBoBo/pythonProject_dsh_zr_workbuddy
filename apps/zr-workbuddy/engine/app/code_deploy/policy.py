"""部署策略：严格二元判定 —— 全量 或 增量，没有「建议全量」中间态。

契约（必须同时满足 UI / prepare / confirm）：
1. 触发全量条件 → mode=full 且 force_full=True，禁止改增量；确认时同步目录全部单元。
2. 否则 → mode=incremental 且 force_full=False；确认时只同步 diff 命中单元。
3. 增量任务允许人「升级」为全量（安全方向）；禁止把强制全量降为增量。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .units import DeployUnit, path_to_unit_id

# 触及即强制全量（整仓脚手架 / 宿主）。业务映射单元（engine/bridge/feature）不在此列。
_FORCE_FULL_PATH_RE = re.compile(
    r"("
    r"^scripts/"
    r"|^vendor/"
    r"|^AGENTS\.md$"
    r"|^package\.json$"
    r"|^pnpm-lock\.yaml$"
    r"|^\.dsh/profiles/"
    r"|cordis\.patch"
    r")",
    re.I,
)

_CRITICAL_UNMAPPED_RE = re.compile(
    r"^apps/zr-workbuddy/(features|plugins|engine)/",
    re.I,
)

_SKIP_UNMAPPED_RE = re.compile(
    r"("
    r"^docs/"
    r"|^apps/zr-workbuddy/engine/data/"
    r"|/config\.yaml$"
    r"|\.pyc$"
    r"|__pycache__"
    r"|\.DS_Store$"
    r"|^\.git/"
    r")",
    re.I,
)

# 命中单元数达到此阈值 → 强制全量（不再有「建议全量可改增量」）
_FORCE_FULL_UNIT_COUNT = 6


@dataclass
class DeployDecision:
    mode: str  # 仅 full | incremental
    force_full: bool
    first_deploy: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # 仅增量时可升级为全量；强制全量时恒为 False
    allow_upgrade_to_full: bool = False

    @property
    def recommend_full(self) -> bool:
        """兼容旧字段：二元策略下恒为 False。"""
        return False

    @property
    def allow_mode_override(self) -> bool:
        """兼容旧字段：仅表示「可升级全量」，不可降级为增量。"""
        return self.allow_upgrade_to_full

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "force_full": self.force_full,
            "recommend_full": False,
            "first_deploy": self.first_deploy,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "allow_mode_override": self.allow_upgrade_to_full,
            "allow_upgrade_to_full": self.allow_upgrade_to_full,
            "locked": bool(self.force_full and self.mode == "full"),
        }


def _norm(p: str) -> str:
    return (p or "").replace("\\", "/").strip().lstrip("./")


def collect_unmapped_critical(paths: list[str]) -> list[str]:
    out: list[str] = []
    for raw in paths:
        p = _norm(raw)
        if not p or path_to_unit_id(p) is not None:
            continue
        if _SKIP_UNMAPPED_RE.search(p):
            continue
        if _CRITICAL_UNMAPPED_RE.search(p) or _FORCE_FULL_PATH_RE.search(p):
            out.append(p)
    return out[:40]


def _full(
    *,
    first: bool,
    reasons: list[str],
    warnings: list[str],
) -> DeployDecision:
    return DeployDecision(
        mode="full",
        force_full=True,
        first_deploy=first,
        reasons=reasons or ["策略判定：强制全量"],
        warnings=warnings,
        allow_upgrade_to_full=False,
    )


def _incremental(
    *,
    first: bool,
    reasons: list[str],
    warnings: list[str],
) -> DeployDecision:
    return DeployDecision(
        mode="incremental",
        force_full=False,
        first_deploy=first,
        reasons=reasons,
        warnings=warnings,
        allow_upgrade_to_full=True,
    )


def decide_deploy_mode(
    *,
    last_sha: str,
    base_resolved: bool,
    paths: list[str],
    units: list[DeployUnit],
    dirty_paths: list[str] | None = None,
    remote_empty: bool | None = None,
    remote_probe_error: str = "",
) -> DeployDecision:
    """二元判定：满足任一强制条件 → 全量；否则 → 增量。"""
    reasons: list[str] = []
    warnings: list[str] = []
    first = not bool((last_sha or "").strip())
    all_paths = [_norm(p) for p in (paths or []) if _norm(p)]
    dirty = [_norm(p) for p in (dirty_paths or []) if _norm(p)]

    force_reasons: list[str] = []

    if first:
        force_reasons.append("无上次成功部署记录（last_deploy.json），按首次全量处理")
    elif not base_resolved:
        force_reasons.append("上次部署 SHA 无法在本仓库解析（可能 rebase/换仓），强制全量以免漏文件")

    if remote_empty is True:
        force_reasons.append("远端应用目录为空或不存在，强制全量")
    elif remote_probe_error:
        warnings.append(f"远端探测未完成：{remote_probe_error}（仍按本机变更策略）")

    force_hits = [p for p in all_paths if _FORCE_FULL_PATH_RE.search(p)]
    if force_hits:
        sample = "、".join(force_hits[:5])
        force_reasons.append(f"变更触及脚手架路径，强制全量：{sample}")

    unmapped = collect_unmapped_critical(all_paths)
    if unmapped:
        sample = "、".join(unmapped[:5])
        force_reasons.append(f"存在未映射到部署单元的关键路径，强制全量：{sample}")

    dirty_unmapped = collect_unmapped_critical(dirty)
    if dirty_unmapped:
        sample = "、".join(dirty_unmapped[:5])
        force_reasons.append(f"未提交变更含未映射关键路径，强制全量：{sample}")

    kinds = {u.kind for u in units}
    unit_n = len(units)

    if "scripts" in kinds and ("engine" in kinds or "bridge" in kinds):
        force_reasons.append("同时变更 scripts 与引擎/bridge，强制全量保证远端可重启")

    if unit_n >= _FORCE_FULL_UNIT_COUNT:
        force_reasons.append(
            f"命中部署单元 {unit_n} 个（≥{_FORCE_FULL_UNIT_COUNT}），强制全量降低漏配风险"
        )

    if dirty:
        warnings.append(
            f"工作区有 {len(dirty)} 个未提交变更已纳入对比；"
            "与上次成功部署内容相同的脏文件会被自动忽略"
        )

    if force_reasons:
        return _full(first=first, reasons=force_reasons, warnings=warnings)

    if not units and not first:
        reasons.append("相对上次部署无业务单元变更；确认将不 rsync（可升级为全量）")
        return _incremental(
            first=first,
            reasons=reasons,
            warnings=warnings + ["无增量单元可同步；若远端异常请改用全量"],
        )

    ids = "、".join(u.id for u in units) or "（无）"
    reasons.append(f"相对上次部署仅命中：{ids}，采用增量自动全选这些单元")
    return _incremental(first=first, reasons=reasons, warnings=warnings)


def apply_user_mode_override(
    decision: DeployDecision,
    requested: str,
) -> DeployDecision:
    """人覆盖：仅允许增量→全量升级；强制全量禁止降级。"""
    req = (requested or "").strip().lower()
    if req in {"auto", ""}:
        return decision
    if req in {"full", "all", "全量"}:
        if decision.mode == "full":
            return decision
        # 增量升级全量（仍非 force，确认后可再改回？为成熟机制：升级后本 job 视为全量且可确认）
        return DeployDecision(
            mode="full",
            force_full=False,
            first_deploy=decision.first_deploy,
            reasons=list(decision.reasons) + ["用户升级为全量"],
            warnings=list(decision.warnings),
            allow_upgrade_to_full=False,
        )
    if req in {"incremental", "incr", "diff", "增量"}:
        if decision.force_full or decision.mode == "full" and not decision.allow_upgrade_to_full:
            # 强制全量或已锁定全量：拒绝降级
            if decision.force_full:
                return DeployDecision(
                    mode="full",
                    force_full=True,
                    first_deploy=decision.first_deploy,
                    reasons=list(decision.reasons),
                    warnings=list(decision.warnings)
                    + ["已拒绝改选增量：当前必须全量部署"],
                    allow_upgrade_to_full=False,
                )
            # 用户曾升级全量，再改回增量：允许（仍是安全可逆于升级前）
            return DeployDecision(
                mode="incremental",
                force_full=False,
                first_deploy=decision.first_deploy,
                reasons=list(decision.reasons) + ["用户改回增量"],
                warnings=list(decision.warnings),
                allow_upgrade_to_full=True,
            )
        return decision
    return decision


def resolve_execution_plan(
    *,
    mode: str,
    force_full: bool,
    units_full: list[dict[str, Any]],
    units_incremental: list[dict[str, Any]],
) -> dict[str, Any]:
    """由已判定 mode 生成执行计划：确认时必须按此集合同步。"""
    m = "full" if (force_full or mode == "full") else "incremental"
    if m == "full":
        ids = [
            str(u.get("id") or "").strip()
            for u in (units_full or [])
            if isinstance(u, dict) and u.get("id")
        ]
    else:
        ids = [
            str(u.get("id") or "").strip()
            for u in (units_incremental or [])
            if isinstance(u, dict) and u.get("id")
        ]
    return {
        "mode": m,
        "unit_ids": ids,
        "locked": bool(force_full),
        "unit_count": len(ids),
    }


def resolve_confirm_mode(
    *,
    job_mode: str,
    force_full: bool,
    requested_mode: str | None,
) -> tuple[str, str]:
    """确认时解析最终 mode。

    返回 (mode, error)。error 非空表示拒绝。
    """
    req = (requested_mode or "").strip().lower()
    if force_full:
        if req in {"incremental", "incr", "diff", "增量"}:
            return "full", "当前变更必须全量部署，不能改选增量"
        return "full", ""
    # 非强制：默认跟 job；允许升级全量；允许从升级后改回增量
    base = "full" if (job_mode or "").lower() == "full" else "incremental"
    if req in {"full", "all", "全量"}:
        return "full", ""
    if req in {"incremental", "incr", "diff", "增量"}:
        return "incremental", ""
    if req in {"", "auto"}:
        return base, ""
    return base, ""
