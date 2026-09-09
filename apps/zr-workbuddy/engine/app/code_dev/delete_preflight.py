"""删除类任务预检：本机已达成目标时跳过 Cursor，避免 10+ 分钟空读盘。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .brief import infer_target_from_text, is_delete_intent
from .delete_verify import _FEATURE_ORPHAN_FILES, extract_delete_features

# 预检只读这些路径（存在则查），毫秒级完成
_DEFAULT_PROBE_FILES = (
    "frontend/src/layouts/AppLayout.vue",
    "frontend/src/router/index.js",
    "frontend/src/api/quality.js",
    "frontend/src/api/qualityInspectionPlans.js",
    "backend/app/routers/quality.py",
    "backend/app/permissions.py",
)

_OVERVIEW_VIEW_CANDIDATES = (
    "frontend/src/views/quality-management/Index.vue",
    "frontend/src/views/quality-management/QualityOverviewView.vue",
    "frontend/src/views/quality-management/Overview.vue",
)


def _feature_label(requirement: str) -> str:
    feats = extract_delete_features(requirement)
    return feats[0] if feats else ""


def _read_rel(root: Path, rel: str, *, limit: int = 400_000) -> str | None:
    p = root / rel.replace("\\", "/").lstrip("/")
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return raw[:limit]


def _probe_paths(requirement: str) -> list[str]:
    hints = infer_target_from_text(requirement)
    paths: list[str] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        r = str(rel or "").replace("\\", "/").strip().lstrip("/")
        if not r or r in seen:
            return
        seen.add(r)
        paths.append(r)

    for p in hints.get("expected_paths") or []:
        add(p)
    for p in _DEFAULT_PROBE_FILES:
        add(p)
    for p in _OVERVIEW_VIEW_CANDIDATES:
        add(p)
    for feat in extract_delete_features(requirement):
        for p in _FEATURE_ORPHAN_FILES.get(feat, ()):
            add(p)
    return paths[:40]


def audit_delete_target(
    target_root: Path,
    requirement: str,
) -> dict[str, Any]:
    """
    扫描本机工程是否仍含待删功能痕迹。
    返回 skip_cursor=True 表示无需再跑 Cursor（通常 <2s）。
    失败闭合：解析不出叶子功能名 / 探针不足 / 仍有命中 → 不跳过。
    """
    root = Path(target_root).resolve()
    if not is_delete_intent(requirement):
        return {"skip_cursor": False, "delivery": "", "checks": [], "feature": ""}

    features = extract_delete_features(requirement)
    feature = features[0] if features else ""
    if not feature:
        return {
            "skip_cursor": False,
            "delivery": "",
            "checks": [],
            "feature": "",
            "reason": "feature_unresolved",
        }

    checks: list[dict[str, str]] = []
    probes_read = 0

    for feat in features:
        for rel in _FEATURE_ORPHAN_FILES.get(feat, ()):
            if (root / rel).is_file():
                checks.append(
                    {
                        "kind": "orphan_file",
                        "path": rel,
                        "detail": f"「{feat}」页面/API 仍存在",
                    }
                )
        if feat == "品质概览" or "概览" in feat:
            for rel in _OVERVIEW_VIEW_CANDIDATES:
                if (root / rel).is_file():
                    checks.append(
                        {"kind": "orphan_file", "path": rel, "detail": "页面/占位文件仍存在"}
                    )

    for rel in _probe_paths(requirement):
        text = _read_rel(root, rel)
        if text is None:
            continue
        probes_read += 1
        for feat in features:
            if feat and feat in text:
                checks.append({"kind": "text_hit", "path": rel, "detail": f"仍含「{feat}」"})
        if feature and "概览" in feature:
            if "fetchQualityOverview" in text:
                checks.append({"kind": "api_fn", "path": rel, "detail": "仍含 fetchQualityOverview"})
            if re.search(r"/api/quality/overview|quality/overview", text, re.I):
                checks.append({"kind": "api_route", "path": rel, "detail": "仍含 overview 接口"})
            if re.search(r"QualityManagementIndex|quality-management['\"]?\s*,\s*component", text):
                checks.append({"kind": "route", "path": rel, "detail": "仍含概览路由组件"})

    # 探针文件一个都没读到 → 无法证明已删干净，禁止跳过 Cursor
    if probes_read < 2:
        return {
            "skip_cursor": False,
            "delivery": "",
            "checks": [],
            "feature": feature,
            "reason": "probe_insufficient",
        }

    # 去重
    uniq: list[dict[str, str]] = []
    seen_k: set[tuple[str, str]] = set()
    for c in checks:
        key = (c.get("path") or "", c.get("kind") or "")
        if key in seen_k:
            continue
        seen_k.add(key)
        uniq.append(c)

    if uniq:
        return {
            "skip_cursor": False,
            "delivery": "",
            "checks": uniq,
            "feature": feature,
        }

    label = feature or "目标功能"
    delivery = (
        "## 说明方案\n\n"
        "**结论**\n"
        f"经引擎预检本机工程，{label}相关菜单、路由、页面与 API 引用均已不存在，"
        "目标状态已达成，本次无需再调用 Cursor 改码。\n\n"
        "**改动文件**\n"
        "- 无：预检通过，未产生代码 diff\n\n"
        "**行为约定**\n"
        f"- 已删除（此前已完成）：「{label}」相关菜单入口、路由与页面\n"
        "- 保留：同模块其余子功能与其 API 未改动\n"
        "- 未改动：其它业务模块\n\n"
        "**验收**\n"
        f"1. 登录后在对应模块菜单中确认无「{label}」\n"
        "2. 访问原路由应重定向或 404\n"
        "3. 同模块其余子页面与接口正常\n"
    )
    return {
        "skip_cursor": True,
        "delivery": delivery,
        "checks": [],
        "feature": feature,
    }


def delivery_indicates_already_done(assistant_text: str) -> bool:
    """Cursor 终稿表明「已达成 / 无需再改」。"""
    t = (assistant_text or "").strip()
    if not t:
        return False
    if "说明方案" not in t and "结论" not in t and "一句话结论" not in t:
        return False
    markers = (
        "目标状态已达成",
        "此前已完成",
        "未产生代码 diff",
        "未产生任何文件变更",
        "无需再",
        "无需额外",
        "本次未产生",
        "无：目标",
        "已无",
        "不存在",
        "未改动",
    )
    return any(m in t for m in markers)
