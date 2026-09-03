"""部署策略：对比上次成功部署记录，自动判定全量 / 增量（人只触发确认）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .units import DeployUnit, path_to_unit_id

# 触及即强制全量（整仓脚手架 / 宿主依赖）。
# 注意：engine/requirements.txt、runtime.yaml、bridge 源码等已映射到 engine/bridge 单元，
# 由对应单元增量同步 + 引擎重启/远端 venv 安装即可，禁止因此锁死「全仓全量」。
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

# 业务仓内未映射路径：可能漏发 → 强制全量
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

_FORCE_FULL_UNIT_COUNT = 6
_RECOMMEND_FULL_UNIT_COUNT = 4


@dataclass
class DeployDecision:
    mode: str  # full | incremental
    force_full: bool
    recommend_full: bool
    first_deploy: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    allow_mode_override: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "force_full": self.force_full,
            "recommend_full": self.recommend_full,
            "first_deploy": self.first_deploy,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "allow_mode_override": self.allow_mode_override,
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
    """根据上次部署 SHA 对比结果自动判定。

    - 无记录 / 基线失效 / 远端空 / 触及脚手架或未映射关键路径 → 强制全量
    - 变更面过大 → 默认全量并提示（可覆盖）
    - 否则增量，单元 = diff 命中集合（自动全选）
    """
    reasons: list[str] = []
    warnings: list[str] = []
    first = not bool((last_sha or "").strip())
    all_paths = [_norm(p) for p in (paths or []) if _norm(p)]
    dirty = [_norm(p) for p in (dirty_paths or []) if _norm(p)]

    force = False
    recommend = False

    if first:
        force = True
        reasons.append("无上次成功部署记录（last_deploy.json），按首次全量处理")
    elif not base_resolved:
        force = True
        reasons.append("上次部署 SHA 无法在本仓库解析（可能 rebase/换仓），强制全量以免漏文件")

    if remote_empty is True:
        force = True
        reasons.append("远端应用目录为空或不存在，强制全量")
    elif remote_probe_error:
        warnings.append(f"远端探测未完成：{remote_probe_error}（仍按本机变更策略）")

    force_hits = [p for p in all_paths if _FORCE_FULL_PATH_RE.search(p)]
    if force_hits:
        force = True
        sample = "、".join(force_hits[:5])
        reasons.append(f"变更触及脚手架/依赖路径，强制全量：{sample}")

    unmapped = collect_unmapped_critical(all_paths)
    if unmapped:
        force = True
        sample = "、".join(unmapped[:5])
        reasons.append(f"存在未映射到部署单元的关键路径，增量可能漏发，强制全量：{sample}")

    kinds = {u.kind for u in units}
    feature_n = sum(1 for u in units if u.kind == "feature")
    unit_n = len(units)

    if "scripts" in kinds and ("engine" in kinds or "bridge" in kinds):
        force = True
        reasons.append("同时变更 scripts 与引擎/bridge，强制全量保证远端可重启")

    if unit_n >= _FORCE_FULL_UNIT_COUNT:
        force = True
        reasons.append(
            f"命中部署单元 {unit_n} 个（≥{_FORCE_FULL_UNIT_COUNT}），强制全量降低漏配风险"
        )
    elif unit_n >= _RECOMMEND_FULL_UNIT_COUNT or (
        feature_n >= 3 and ("engine" in kinds or "bridge" in kinds)
    ):
        # engine+bridge 同改不再默认全量：两单元增量即可，避免「已部署过仍锁全量」
        recommend = True
        reasons.append(
            f"变更面较大（单元 {unit_n}，feature {feature_n}，含 "
            f"{', '.join(sorted(kinds)) or '无'}），建议全量；确认卡默认全量"
        )

    if dirty:
        warnings.append(
            f"工作区有 {len(dirty)} 个未提交变更已纳入对比；"
            "与上次成功部署内容相同的脏文件会被自动忽略"
        )
        dirty_unmapped = collect_unmapped_critical(dirty)
        if dirty_unmapped and not force:
            recommend = True
            reasons.append("未提交变更含未映射关键路径，建议全量")

    if force:
        return DeployDecision(
            mode="full",
            force_full=True,
            recommend_full=True,
            first_deploy=first,
            reasons=reasons or ["策略判定：强制全量"],
            warnings=warnings,
            allow_mode_override=False,
        )

    if recommend:
        return DeployDecision(
            mode="full",
            force_full=False,
            recommend_full=True,
            first_deploy=first,
            reasons=reasons,
            warnings=warnings,
            allow_mode_override=True,
        )

    if not units and not first:
        reasons.append("相对上次部署无业务单元变更；若远端异常可改用全量")
        return DeployDecision(
            mode="incremental",
            force_full=False,
            recommend_full=False,
            first_deploy=first,
            reasons=reasons,
            warnings=warnings + ["无增量单元可同步；确认将不会 rsync（可改选全量）"],
            allow_mode_override=True,
        )

    ids = "、".join(u.id for u in units) or "（无）"
    reasons.append(f"相对上次部署仅命中：{ids}，采用增量自动全选这些单元")
    return DeployDecision(
        mode="incremental",
        force_full=False,
        recommend_full=False,
        first_deploy=first,
        reasons=reasons,
        warnings=warnings,
        allow_mode_override=True,
    )


def apply_user_mode_override(
    decision: DeployDecision,
    requested: str,
) -> DeployDecision:
    """人覆盖模式：强制全量时拒绝改增量；建议全量时可改增量但留警告。"""
    req = (requested or "").strip().lower()
    if req in {"auto", ""}:
        return decision
    if req in {"full", "all", "全量"}:
        if decision.mode == "full":
            return decision
        return DeployDecision(
            mode="full",
            force_full=decision.force_full,
            recommend_full=True,
            first_deploy=decision.first_deploy,
            reasons=list(decision.reasons) + ["用户改选全量"],
            warnings=list(decision.warnings),
            allow_mode_override=decision.allow_mode_override,
        )
    if req in {"incremental", "incr", "diff", "增量"}:
        if decision.force_full:
            return DeployDecision(
                mode="full",
                force_full=True,
                recommend_full=True,
                first_deploy=decision.first_deploy,
                reasons=list(decision.reasons),
                warnings=list(decision.warnings)
                + ["已拒绝改选增量：当前变更必须全量部署"],
                allow_mode_override=False,
            )
        return DeployDecision(
            mode="incremental",
            force_full=False,
            recommend_full=decision.recommend_full,
            first_deploy=decision.first_deploy,
            reasons=list(decision.reasons) + ["用户改选增量（自担漏发风险）"],
            warnings=list(decision.warnings)
            + (["策略曾建议全量，已改增量"] if decision.recommend_full else []),
            allow_mode_override=True,
        )
    return decision
