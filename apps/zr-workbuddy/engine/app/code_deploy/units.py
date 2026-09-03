"""部署单元：把路径映射为可独立同步的插件/层。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# apps/zr-workbuddy/features/<id>/...
_FEATURE_RE = re.compile(
    r"^apps/zr-workbuddy/features/([a-z][a-z0-9_-]*)(?:/|$)"
)


@dataclass(frozen=True)
class DeployUnit:
    id: str
    kind: str  # feature | engine | bridge | skills | scripts
    label: str
    local_rels: tuple[str, ...]  # 相对仓库根，rsync 源
    action: str  # sync_feature | sync_engine_restart | sync_bridge_reinstall | sync_only
    risk: str  # low | medium | high
    selected: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "local_rels": list(self.local_rels),
            "action": self.action,
            "risk": self.risk,
            "selected": self.selected,
            "action_hint": _action_hint(self.action),
        }


def _action_hint(action: str) -> str:
    return {
        "sync_feature": "仅同步插件目录，热加载，不重启",
        "sync_engine_restart": "同步引擎代码后重启引擎进程",
        "sync_bridge_reinstall": "同步 bridge 后重装并重启 DSH",
        "sync_only": "仅同步文件",
    }.get(action, action)


def _norm(rel: str) -> str:
    r = (rel or "").replace("\\", "/").strip()
    while r.startswith("./"):
        r = r[2:]
    return r.lstrip("/")


def path_to_unit_id(rel: str) -> str | None:
    """单文件相对路径 → 单元 id；docs 等返回 None（默认不部署）。"""
    r = _norm(rel)
    if not r:
        return None
    m = _FEATURE_RE.match(r)
    if m:
        return f"feature:{m.group(1)}"
    if r.startswith("apps/zr-workbuddy/plugins/mes-bridge/") or r.startswith(
        "apps/zr-workbuddy/plugins/mes-runtime/"
    ):
        return "bridge"
    if (
        r.startswith("apps/zr-workbuddy/engine/app/")
        or r == "apps/zr-workbuddy/engine/engine_cli.py"
        or r == "apps/zr-workbuddy/engine/requirements.txt"
        or r.startswith("apps/zr-workbuddy/engine/tests/")
    ):
        # 静态面板也算引擎侧
        if "engine/data/" in r or r.startswith("apps/zr-workbuddy/engine/data/"):
            return None
        return "engine"
    if r.startswith("apps/zr-workbuddy/engine/app/static/"):
        return "engine"
    if r.startswith(".dsh/skills/"):
        return "skills"
    if r.startswith("scripts/"):
        return "scripts"
    return None


def build_unit(unit_id: str, *, selected: bool = True) -> DeployUnit | None:
    uid = (unit_id or "").strip()
    if uid.startswith("feature:"):
        fid = uid.split(":", 1)[1].strip()
        if not re.match(r"^[a-z][a-z0-9_-]*$", fid):
            return None
        return DeployUnit(
            id=uid,
            kind="feature",
            label=f"插件 {fid}",
            local_rels=(f"apps/zr-workbuddy/features/{fid}",),
            action="sync_feature",
            risk="low",
            selected=selected,
        )
    if uid == "engine":
        return DeployUnit(
            id="engine",
            kind="engine",
            label="引擎（Python / SPA）",
            local_rels=(
                "apps/zr-workbuddy/engine/app",
                "apps/zr-workbuddy/engine/engine_cli.py",
                "apps/zr-workbuddy/engine/requirements.txt",
            ),
            action="sync_engine_restart",
            risk="medium",
            selected=selected,
        )
    if uid == "bridge":
        return DeployUnit(
            id="bridge",
            kind="bridge",
            label="mes-bridge + mes-runtime",
            local_rels=(
                "apps/zr-workbuddy/plugins/mes-bridge",
                "apps/zr-workbuddy/plugins/mes-runtime",
            ),
            action="sync_bridge_reinstall",
            risk="high",
            selected=selected,
        )
    if uid == "skills":
        return DeployUnit(
            id="skills",
            kind="skills",
            label="Agent Skills",
            local_rels=(".dsh/skills",),
            action="sync_only",
            risk="low",
            selected=selected,
        )
    if uid == "scripts":
        return DeployUnit(
            id="scripts",
            kind="scripts",
            label="运维脚本 scripts/",
            local_rels=("scripts",),
            action="sync_only",
            risk="low",
            selected=selected,
        )
    return None


def map_paths_to_units(paths: list[str]) -> list[DeployUnit]:
    """变更路径 → 去重后的部署单元（默认全选）。"""
    order: list[str] = []
    seen: set[str] = set()
    for p in paths:
        uid = path_to_unit_id(p)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        order.append(uid)
    # 执行顺序：feature → skills/scripts → engine → bridge
    rank = {"feature": 0, "skills": 1, "scripts": 2, "engine": 3, "bridge": 4}

    def sort_key(uid: str) -> tuple[int, str]:
        u = build_unit(uid)
        kind = u.kind if u else "z"
        return (rank.get(kind, 9), uid)

    order.sort(key=sort_key)
    out: list[DeployUnit] = []
    for uid in order:
        u = build_unit(uid, selected=True)
        if u:
            out.append(u)
    return out


def filter_units_by_ids(units: list[DeployUnit], selected_ids: list[str] | None) -> list[DeployUnit]:
    """按人勾选过滤；None/空 = 保持 prepare 时 selected 标记。"""
    if selected_ids is None:
        return [u for u in units if u.selected]
    want = {str(x).strip() for x in selected_ids if str(x).strip()}
    if not want:
        return []
    out: list[DeployUnit] = []
    for u in units:
        if u.id in want:
            out.append(
                DeployUnit(
                    id=u.id,
                    kind=u.kind,
                    label=u.label,
                    local_rels=u.local_rels,
                    action=u.action,
                    risk=u.risk,
                    selected=True,
                )
            )
    return out


def list_catalog_units(workspace: Path | str | None = None) -> list[DeployUnit]:
    """全量目录：扫描 features/* + engine/bridge/skills/scripts（存在才纳入）。"""
    root = Path(workspace or ".").expanduser()
    try:
        root = root.resolve()
    except OSError:
        root = Path(".")

    ids: list[str] = []
    feat_root = root / "apps" / "zr-workbuddy" / "features"
    if feat_root.is_dir():
        for d in sorted(feat_root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if not re.match(r"^[a-z][a-z0-9_-]*$", d.name):
                continue
            if (d / "index.js").is_file() or (d / "manifest.json").is_file():
                ids.append(f"feature:{d.name}")

    for uid in ("skills", "scripts", "engine", "bridge"):
        u = build_unit(uid)
        if not u:
            continue
        # 至少有一个本地路径存在才列入
        if any((root / rel).exists() for rel in u.local_rels):
            ids.append(uid)

    out: list[DeployUnit] = []
    seen: set[str] = set()
    rank = {"feature": 0, "skills": 1, "scripts": 2, "engine": 3, "bridge": 4}

    def sort_key(uid: str) -> tuple[int, str]:
        bu = build_unit(uid)
        kind = bu.kind if bu else "z"
        return (rank.get(kind, 9), uid)

    for uid in sorted(ids, key=sort_key):
        if uid in seen:
            continue
        seen.add(uid)
        built = build_unit(uid, selected=True)
        if built:
            out.append(built)
    return out
