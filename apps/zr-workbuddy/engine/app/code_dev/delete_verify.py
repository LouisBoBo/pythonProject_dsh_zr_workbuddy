"""删除类任务：同步后在目标工程验尸，避免「文案已删、磁盘/界面仍在」假成功。"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .brief import infer_target_from_text, is_delete_intent

_MENU_PROBE_FILES = (
    "frontend/src/layouts/AppLayout.vue",
    "frontend/src/router/index.js",
)

_FEATURE_ORPHAN_FILES: dict[str, tuple[str, ...]] = {
    "检验方案": (
        "frontend/src/views/quality-management/InspectionPlansView.vue",
        "frontend/src/api/qualityInspectionPlans.js",
    ),
    "检验任务": (
        "frontend/src/views/quality-management/InspectionTasksView.vue",
        "frontend/src/views/production/InspectionTasksView.vue",
        "frontend/src/api/qualityInspectionTasks.js",
    ),
    # 仅删列表页：qualityInspectionRecords.js 被「录入检验」共用，禁止列入
    "检验记录": (
        "frontend/src/views/quality-management/InspectionRecordsView.vue",
        "frontend/src/views/production/InspectionRecordsView.vue",
    ),
    "品质概览": (
        "frontend/src/views/quality-management/Index.vue",
        "frontend/src/views/quality-management/QualityOverviewView.vue",
        "frontend/src/views/quality-management/Overview.vue",
    ),
    "生产排产": (
        "frontend/src/views/production/ProductionSchedulingView.vue",
        "frontend/src/api/productionScheduling.js",
        "frontend/src/api/scheduling.js",
    ),
    "请假管理": (
        "frontend/src/views/attendance/LeaveView.vue",
        "frontend/src/api/attendanceLeave.js",
        "frontend/src/api/leave.js",
    ),
    # 看板页：仅登记主页面作 Cursor 空清单时的兜底；API/后端以过程「删除清单」动态提取
    "仓储看板": (
        "frontend/src/views/board/WarehouseDashboard.vue",
    ),
    "生产看板": (
        "frontend/src/views/board/ProductionDashboard.vue",
        "frontend/src/views/kanban/ProductionKanbanView.vue",
    ),
    "品质看板": (
        "frontend/src/views/board/QualityDashboard.vue",
        "frontend/src/views/kanban/QualityKanbanView.vue",
    ),
    "设备看板": (
        "frontend/src/views/board/DeviceDashboard.vue",
        "frontend/src/views/kanban/EquipmentKanbanView.vue",
    ),
    "综合看板": (
        "frontend/src/views/board/GeneralDashboard.vue",
        "frontend/src/views/kanban/ComprehensiveKanbanView.vue",
    ),
}

_FEATURE_ROUTE_MARKERS: dict[str, tuple[str, ...]] = {
    "检验方案": ("quality-management/inspection-plans", "InspectionPlansView"),
    "检验任务": (
        "quality-management/inspection-tasks",
        "quality-inspection-tasks",
        "InspectionTasksView",
        "qualityInspectionTasks",
    ),
    "检验记录": (
        "quality-management/inspection-records",
        "quality-inspection-records",
        "InspectionRecordsView",
    ),
    "品质概览": (
        "QualityOverview",
        "quality-overview",
        "quality-management/index",
        "QualityManagementIndex",
    ),
    "生产排产": (
        "production/scheduling",
        "production-scheduling",
        "ProductionScheduling",
        "ProductionSchedulingView",
    ),
    "请假管理": (
        "attendance/leave",
        "attendance-leave",
        "AttendanceLeave",
        "LeaveView",
    ),
    "仓储看板": (
        "kanban/warehouse",
        "WarehouseDashboard",
        "warehouse-dashboard",
    ),
    "生产看板": (
        "kanban/production",
        "ProductionDashboard",
        "ProductionKanban",
    ),
    "品质看板": (
        "quality/dashboard",
        "QualityDashboard",
        "QualityKanban",
    ),
    "设备看板": (
        "kanban/equipment",
        "DeviceDashboard",
        "EquipmentKanban",
    ),
    "综合看板": (
        "kanban/general",
        "GeneralDashboard",
        "ComprehensiveKanban",
    ),
}

# 已知菜单叶子名：优先从长诉求里抠出这些，避免「生产管理菜单下的生产排产」整串验尸假阴性
_KNOWN_MENU_LEAVES = (
    "生产排产",
    "生产工单",
    "品质概览",
    "检验方案",
    "检验任务",
    "检验记录",
    "录入检验",
    "设备台账",
    "设备点检",
    "保养计划",
    "保养工单",
    "维修管理",
    "物料库存",
    "物料入库",
    "物料出库",
    "考勤记录",
    "请假管理",
    "排班管理",
    "生产看板",
    "品质看板",
    "设备看板",
    "仓储看板",
    "综合看板",
)

_RUNTIME_HINT = (
    "【界面刷新】本机源码已写入；若本机 Vite 在跑，WorkBuddy 已自动软重启前端热更新服务。"
    "请硬刷新浏览器（Cmd+Shift+R）即可看到菜单/路由变化，一般无需再手动 Ctrl+C 重启 `npm run dev`。"
    "本机开发入口一般为 http://127.0.0.1:5175（以 vite.config.js 为准）。"
    "若您打开的是远端部署地址（非 localhost），还须走「部署上线」同步到服务器。"
)


def extract_delete_features(requirement: str) -> list[str]:
    """从诉求中提取待删功能/菜单名（可多个）。优先叶子名，禁止整段「某某菜单下的xxx」当验尸键。"""
    text = (requirement or "").strip()
    if not text:
        return []
    # 去掉 canonical 模板噪声，避免「原始诉求」被当成功能名
    text = re.sub(r"【[^】]{1,24}】", " ", text)
    text = re.sub(
        r"必须完整实现「原始诉求」中的业务目标[^\n]*",
        " ",
        text,
    )
    found: list[str] = []

    def _norm(label: str) -> str:
        s = (label or "").strip()
        for prefix in ("菜单下的", "模块下的", "里的", "中的", "下的", "请求中"):
            if prefix in s:
                s = s.split(prefix)[-1].strip()
        for suffix in ("功能", "页面", "菜单", "模块", "入口", "路由", "子项", "子菜单"):
            if s.endswith(suffix) and len(s) > len(suffix) + 1:
                s = s[: -len(suffix)].strip()
        for parent in ("生产管理", "品质管理", "质量管理", "设备管理", "仓储管理", "看板管理", "考勤管理", "业务管理"):
            if s.startswith(parent) and len(s) > len(parent) + 1:
                s = s[len(parent) :].lstrip("的下中里-—– ")
        return s.strip(" 「」『』\"'")

    # 1) 已知叶子名直接命中（最短可靠）
    for leaf in _KNOWN_MENU_LEAVES:
        if leaf in text:
            found.append(leaf)

    # 若已命中已知菜单名，不再用兜底正则（避免「原始诉求」「页面与」等噪声）
    if found:
        out: list[str] = []
        seen: set[str] = set()
        for f in found:
            if f in seen:
                continue
            seen.add(f)
            out.append(f)
        parents = {"生产管理", "品质管理", "质量管理", "设备管理", "仓储管理", "看板管理", "考勤管理"}
        leaves = [x for x in out if x not in parents]
        return leaves if leaves else out

    # 2) 「…下的生产排产」结构
    for m in re.finditer(r"(?:菜单|模块|管理)?下的\s*[「『\"]?([^」』\"，。\n]{2,16})", text):
        found.append(_norm(m.group(1)))

    # 3) 引号与「删除/移除…」兜底
    for m in re.finditer(r"[「『\"]([^」』\"]{2,24})[」』\"]", text):
        found.append(_norm(m.group(1)))
    for m in re.finditer(r"(?:移除|删除|去掉|下线|清理)\s*[「『\"]?([^」』\"，。\n]{2,24})", text):
        found.append(_norm(m.group(1)))

    blocklist = {
        "原始诉求",
        "实现要点",
        "硬性约束",
        "验收",
        "业务目标",
        "目标模块",
        "通用列表",
        "页面与",
        "菜单与",
    }
    out = []
    seen = set()
    for f in found:
        if len(f) < 2 or f in seen:
            continue
        if f in blocklist or any(b in f for b in blocklist):
            continue
        if "菜单" in f and f not in _KNOWN_MENU_LEAVES:
            continue
        if len(f) > 12 and f not in _KNOWN_MENU_LEAVES:
            continue
        if f not in _KNOWN_MENU_LEAVES and re.search(
            r"那个|这个|东西|相关|对应|上述|目标|功能项|诉求|约束|要点",
            f,
        ):
            continue
        seen.add(f)
        out.append(f)
    parents = {"生产管理", "品质管理", "质量管理", "设备管理", "仓储管理", "看板管理", "考勤管理"}
    leaves = [x for x in out if x not in parents]
    if leaves and any(p in out for p in parents):
        return leaves
    return out


def _read_rel(root: Path, rel: str, *, limit: int = 500_000) -> str | None:
    p = root / rel.replace("\\", "/").lstrip("/")
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return None


def _menu_still_has_feature(text: str, feature: str) -> bool:
    if not text or not feature:
        return False
    if re.search(rf"title:\s*['\"]{re.escape(feature)}['\"]", text):
        return True
    if re.search(rf"meta:\s*\{{[^}}]*title:\s*['\"]{re.escape(feature)}['\"]", text):
        return True
    if feature in text and "children:" in text:
        # 菜单树里出现功能名即视为仍在（避免只靠整串等于）
        if re.search(rf"['\"][^'\"]*{re.escape(feature)}[^'\"]*['\"]", text):
            return True
    for marker in _FEATURE_ROUTE_MARKERS.get(feature, ()):
        if marker.lower() in text.lower():
            return True
    return False


def verify_delete_on_target(
    target_root: Path,
    requirement: str,
    *,
    synced_files: list[str] | None = None,
    deleted_files: list[str] | None = None,
) -> dict[str, Any]:
    """
    同步后在目标工程读盘验尸。
    返回 ok=False 表示磁盘上仍可检出待删菜单/路由/页面 → 任务应判失败。
    默认失败闭合：解析不出功能名 / 读不到探针 → 不得判定「已删除」。
    """
    if not is_delete_intent(requirement):
        return {"ok": True, "detail": "", "runtime_hint": ""}

    root = Path(target_root).resolve()
    features = extract_delete_features(requirement)
    if not features:
        return {
            "ok": False,
            "detail": "无法从诉求解析待删菜单/功能名，禁止判定已删除，须继续定位删除",
            "runtime_hint": "",
            "features": [],
            "inconclusive": True,
        }

    errors: list[str] = []
    probes_ok = 0
    for rel in _MENU_PROBE_FILES:
        body = _read_rel(root, rel)
        if not body:
            continue
        probes_ok += 1
        for feat in features:
            if _menu_still_has_feature(body, feat):
                errors.append(f"{rel} 仍含「{feat}」菜单或路由")

    if probes_ok < 1:
        return {
            "ok": False,
            "detail": "无法读取菜单/路由探针文件，禁止判定已删除",
            "runtime_hint": "",
            "features": features,
            "inconclusive": True,
        }

    for feat in features:
        for rel in _FEATURE_ORPHAN_FILES.get(feat, ()):
            if (root / rel).is_file():
                errors.append(f"页面/API 文件仍存在：{rel}")

    hints = infer_target_from_text(requirement)
    for rel in hints.get("expected_paths") or []:
        rel_s = str(rel).rstrip("/")
        if not rel_s.endswith((".vue", ".js", ".ts", ".tsx")):
            continue
        p = root / rel_s
        if not p.is_file():
            continue
        for feat in features:
            body = _read_rel(root, rel_s) or ""
            if feat in body:
                errors.append(f"{rel_s} 仍含「{feat}」")

    if errors:
        uniq = list(dict.fromkeys(errors))
        return {
            "ok": False,
            "detail": "；".join(uniq[:10]),
            "runtime_hint": "",
            "features": features,
        }

    return {
        "ok": True,
        "detail": "本机工程验尸通过：" + "、".join(f"「{f}」" for f in features) + " 相关菜单/路由/页面已不存在",
        "runtime_hint": _maybe_runtime_hint(synced_files, deleted_files),
        "features": features,
    }


def frontend_runtime_hint(
    synced_files: list[str] | None,
    deleted_files: list[str] | None,
) -> str:
    return _maybe_runtime_hint(synced_files, deleted_files)


def runtime_hint_always() -> str:
    """删除类任务：提示硬刷新即可（WorkBuddy 会先唤醒 Vite，一般不必重启 dev）。"""
    return _RUNTIME_HINT


def _maybe_runtime_hint(
    synced_files: list[str] | None,
    deleted_files: list[str] | None,
) -> str:
    markers = ("frontend/src/layouts/", "frontend/src/router/", "frontend/src/views/")
    touched: list[str] = []
    for raw in list(synced_files or []) + list(deleted_files or []):
        rel = str(raw or "").replace("删除 ", "").replace("\\", "/").strip()
        if any(rel.startswith(m) for m in markers):
            touched.append(rel)
    if not touched:
        return ""
    return _RUNTIME_HINT


def verify_sync_to_target(
    target_root: Path,
    sandbox_root: Path,
    copied_rels: list[str],
    deleted_rels: list[str],
) -> dict[str, Any]:
    """同步后校验：目标文件内容与沙箱一致，应删文件在目标已不存在。"""
    target = Path(target_root).resolve()
    sandbox = Path(sandbox_root).resolve()
    errors: list[str] = []

    for rel in copied_rels or []:
        rel_n = str(rel or "").strip().replace("\\", "/")
        if not rel_n or rel_n.startswith("删除 "):
            continue
        src = sandbox / rel_n
        dst = target / rel_n
        if not src.is_file():
            errors.append(f"沙箱缺失：{rel_n}")
            continue
        if not dst.is_file():
            errors.append(f"未写入目标：{rel_n}")
            continue
        try:
            if hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(dst.read_bytes()).digest():
                errors.append(f"目标内容与沙箱不一致：{rel_n}")
        except OSError as exc:
            errors.append(f"无法校验 {rel_n}：{exc}")

    for rel in deleted_rels or []:
        rel_n = str(rel or "").strip().replace("\\", "/")
        if not rel_n:
            continue
        if (target / rel_n).is_file():
            errors.append(f"应已删除但仍存在：{rel_n}")

    if errors:
        return {"ok": False, "detail": "；".join(errors[:12])}
    return {"ok": True, "detail": ""}
