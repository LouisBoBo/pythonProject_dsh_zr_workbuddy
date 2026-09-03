"""本机审码配置（读 engine config.yaml）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config_store import load_config
from ..health import check_net, llm_ready

# 允许审阅的源码后缀（白名单）；对齐 simplified：不审文档/样式为主对象
ALLOWED_SUFFIXES = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".vue",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".rb",
        ".php",
        ".swift",
        ".sql",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".gradle",
        ".sh",
    }
)

# 明确排除（即便误入白名单也不审）
DOC_OR_STYLE_SUFFIXES = frozenset(
    {
        ".md",
        ".mdx",
        ".txt",
        ".css",
        ".scss",
        ".less",
        ".html",
        ".htm",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".lock",
    }
)

SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".next",
        "coverage",
        ".idea",
        ".vscode",
        "target",
        "out",
        ".vite",
        ".dev-logs",
        ".cursor-sdk-store",
        "local_dev",
        "sandboxes",
    }
)


@dataclass
class CodeReviewConfig:
    enabled: bool = False
    max_files: int = 40
    max_file_bytes: int = 120_000
    max_total_bytes: int = 800_000
    default_workspace: str = ""


def get_config() -> CodeReviewConfig:
    raw = load_config().get("code_review") or {}
    return CodeReviewConfig(
        enabled=bool(raw.get("enabled")),
        max_files=max(1, min(int(raw.get("max_files") or 40), 200)),
        max_file_bytes=max(1024, min(int(raw.get("max_file_bytes") or 120_000), 500_000)),
        max_total_bytes=max(4096, min(int(raw.get("max_total_bytes") or 800_000), 2_000_000)),
        default_workspace=str(raw.get("default_workspace") or "").strip(),
    )


def availability() -> dict[str, Any]:
    cfg = get_config()
    full = load_config()
    if not cfg.enabled:
        return {
            "ok": False,
            "enabled": False,
            "detail": "本机审码未开启：请到引擎「配置中心 → 审码车道」勾选开启并保存",
        }
    if not llm_ready(full):
        return {
            "ok": False,
            "enabled": True,
            "detail": "LLM 未就绪：请在配置中心配置 DeepSeek / Ollama",
        }
    return {
        "ok": True,
        "enabled": True,
        "detail": "本机审码就绪（直读本地文件 + LLM 出报告）",
        "network": check_net(),
    }
