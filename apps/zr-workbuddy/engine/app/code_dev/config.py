"""本机 Cursor Local 写码配置（读 engine config.yaml，不读 simplified 的 .env）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COPY_SKIP_DIR_NAMES = frozenset(
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
    }
)

SENSITIVE_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "credentials.json",
        "service-account.json",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
        "authorized_keys",
        "known_hosts",
        "passwd",
        "shadow",
    }
)

SENSITIVE_SUFFIXES = (".pem", ".p12", ".pfx", ".key", ".ppk")

SENSITIVE_PATH_PARTS = frozenset(
    {
        ".git",
        ".ssh",
        ".gnupg",
        ".aws",
        ".kube",
        ".docker",
    }
)

FORBIDDEN_TARGET_PREFIXES = (
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/var",
    "/System",
    "/Library",
    "/private/etc",
    "/private/var",
    "/Windows",
    "/Program Files",
    "/Program Files (x86)",
)


@dataclass(frozen=True)
class CodeDevConfig:
    enabled: bool = False
    cursor_api_key: str = ""
    model: str = "composer-2.5"
    max_concurrent: int = 1
    max_file_bytes: int = 512_000
    max_changed_files: int = 80
    max_total_write_bytes: int = 2_000_000
    copy_max_files: int = 4000
    copy_max_total_bytes: int = 80_000_000
    cursor_timeout_sec: int = 2700
    default_workspace: str = ""


def _sdk_ok() -> tuple[bool, str]:
    try:
        import cursor_sdk  # noqa: F401

        return True, ""
    except ImportError:
        return False, "未安装 cursor-sdk（请在引擎 venv: pip install cursor-sdk）"
    except Exception as exc:  # noqa: BLE001
        return False, f"cursor-sdk 不可用: {exc}"


def get_config() -> CodeDevConfig:
    from ..config_store import load_config

    root = load_config()
    raw = (root.get("code_dev") or {}) if isinstance(root, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    return CodeDevConfig(
        enabled=bool(raw.get("enabled", False)),
        cursor_api_key=str(raw.get("cursor_api_key") or "").strip(),
        model=(str(raw.get("model") or "composer-2.5").strip() or "composer-2.5"),
        max_concurrent=max(1, int(raw.get("max_concurrent") or 1)),
        max_file_bytes=max(10_000, int(raw.get("max_file_bytes") or 512_000)),
        max_changed_files=max(1, int(raw.get("max_changed_files") or 80)),
        max_total_write_bytes=max(50_000, int(raw.get("max_total_write_bytes") or 2_000_000)),
        copy_max_files=max(100, int(raw.get("copy_max_files") or 4000)),
        copy_max_total_bytes=max(1_000_000, int(raw.get("copy_max_total_bytes") or 80_000_000)),
        cursor_timeout_sec=max(60, int(raw.get("cursor_timeout_sec") or 2700)),
        default_workspace=str(raw.get("default_workspace") or "").strip(),
    )


def availability() -> dict[str, Any]:
    """供 status：不抛异常。"""
    cfg = get_config()
    sdk_ok, sdk_reason = _sdk_ok()
    key_ok = bool(cfg.cursor_api_key)
    ready = bool(cfg.enabled and sdk_ok and key_ok)
    detail_parts = []
    if not cfg.enabled:
        detail_parts.append("未开启（请到引擎配置中心 → 写码车道 勾选开启并保存）")
    if not key_ok:
        detail_parts.append("未配置 Cursor API Key（配置中心 → 写码车道）")
    if not sdk_ok:
        detail_parts.append(sdk_reason)
    return {
        "ok": ready,
        "enabled": cfg.enabled,
        "sdk_ok": sdk_ok,
        "sdk_reason": sdk_reason,
        "has_api_key": key_ok,
        "model": cfg.model,
        "default_workspace": cfg.default_workspace,
        "detail": "就绪" if ready else ("；".join(detail_parts) or "未就绪"),
    }
