"""提交车道配置（读 engine config.yaml 的 code_commit 节）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..config_store import load_config


@dataclass
class CodeCommitConfig:
    enabled: bool = True
    default_workspace: str = ""
    work_branch: str = ""
    remote_name: str = "origin"
    default_push: bool = True
    use_skill_review: bool = True
    allow_blocked: bool = False
    max_files: int = 80


def get_config() -> CodeCommitConfig:
    raw = load_config().get("code_commit") or {}
    # 缺省/未写入时默认开启（总开关仍是功能插件 code-commit）
    enabled = True if "enabled" not in raw else bool(raw.get("enabled"))
    # allow_blocked 仅环境变量，禁止靠 yaml 放行阻断项
    allow_blocked = (os.getenv("CODE_COMMIT_ALLOW_BLOCKED") or "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
    }
    return CodeCommitConfig(
        enabled=enabled,
        default_workspace=str(raw.get("default_workspace") or "").strip(),
        work_branch=str(raw.get("work_branch") or "").strip().strip("/"),
        remote_name=(str(raw.get("remote_name") or "origin").strip() or "origin"),
        default_push=bool(raw.get("default_push", True)),
        use_skill_review=bool(raw.get("use_skill_review", True)),
        allow_blocked=allow_blocked,
        max_files=max(1, min(int(raw.get("max_files") or 80), 200)),
    )


def availability() -> dict[str, Any]:
    cfg = get_config()
    if not cfg.enabled:
        return {
            "ok": False,
            "enabled": False,
            "detail": (
                "提交车道未开启。请用浏览器打开 http://127.0.0.1:8000 "
                "→ 左侧「配置中心」→ 向下滚动到第 7 步「提交车道」→ 勾选开启并保存"
            ),
        }
    return {
        "ok": True,
        "enabled": True,
        "detail": "提交车道就绪（门禁审核 → 人确认 → commit/push）",
        "default_push": cfg.default_push,
        "work_branch": cfg.work_branch or "(空=使用仓库当前分支)",
        "remote_name": cfg.remote_name,
        "max_files": cfg.max_files,
    }
