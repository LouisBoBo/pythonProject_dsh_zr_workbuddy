"""部署车道配置（读 engine config.yaml 的 code_deploy 节；对齐 simplified DEPLOY_*）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config_store import load_config

_SSH_KEY_OK = re.compile(r"^[A-Za-z0-9_./\-]+$")
_HOST_OK = re.compile(r"^[A-Za-z0-9._\-]+$")
_USER_OK = re.compile(r"^[A-Za-z0-9._\-]+$")
_ABS_PATH_OK = re.compile(r"^/[A-Za-z0-9_./\-]+$")


@dataclass
class CodeDeployConfig:
    enabled: bool = False
    provider: str = "local_ssh"  # MVP 仅 local_ssh
    env_whitelist: list[str] = field(default_factory=lambda: ["staging"])
    allow_production: bool = False
    default_env: str = "staging"
    default_workspace: str = ""
    default_ref: str = "HEAD"
    ssh_host: str = ""
    ssh_user: str = ""
    ssh_port: int = 22
    ssh_key_path: str = ""
    ssh_app_path: str = ""  # 远端仓库根（与本仓布局一致）
    health_url: str = ""
    health_timeout_sec: int = 8
    # 远端引擎端口：必须避开服务器已有服务（如本机 8000 常被其它项目占用）
    remote_engine_port: int = 8091
    auto_restart_engine: bool = True
    # 含 bridge 单元时：默认只同步文件（三大目标：业务验收看引擎网页）
    # 确需远端宿主收尾时：config.yaml 显式 auto_restart_bridge: true
    auto_restart_bridge: bool = False
    rsync_excludes: list[str] = field(
        default_factory=lambda: [
            "__pycache__",
            ".venv",
            "venv",
            "*.pyc",
            ".pytest_cache",
            ".env",
            ".env.*",
            "config.yaml",
            "*.pem",
            "id_rsa*",
            "id_ed25519*",
            "*.key",
            ".DS_Store",
            "engine/data",
            "local_dev",
            "sandboxes",
        ]
    )


def get_config() -> CodeDeployConfig:
    raw = load_config().get("code_deploy") or {}
    enabled = bool(raw.get("enabled", False))
    wl_raw = raw.get("env_whitelist") or ["staging"]
    if isinstance(wl_raw, str):
        whitelist = [x.strip().lower() for x in wl_raw.split(",") if x.strip()]
    else:
        whitelist = [str(x).strip().lower() for x in wl_raw if str(x).strip()]
    if not whitelist:
        whitelist = ["staging"]
    allow_prod = bool(raw.get("allow_production", False))
    if not allow_prod:
        whitelist = [e for e in whitelist if e not in {"prod", "production", "生产"}]
        if not whitelist:
            whitelist = ["staging"]
    excludes = raw.get("rsync_excludes")
    cfg = CodeDeployConfig(
        enabled=enabled,
        provider=str(raw.get("provider") or "local_ssh").strip() or "local_ssh",
        env_whitelist=whitelist,
        allow_production=allow_prod,
        default_env=str(raw.get("default_env") or whitelist[0]).strip().lower() or "staging",
        default_workspace=str(raw.get("default_workspace") or "").strip(),
        default_ref=str(raw.get("default_ref") or "HEAD").strip() or "HEAD",
        ssh_host=str(raw.get("ssh_host") or "").strip(),
        ssh_user=str(raw.get("ssh_user") or "").strip(),
        ssh_port=max(1, min(int(raw.get("ssh_port") or 22), 65535)),
        ssh_key_path=str(raw.get("ssh_key_path") or "").strip(),
        ssh_app_path=str(raw.get("ssh_app_path") or "").strip(),
        health_url=str(raw.get("health_url") or "").strip(),
        health_timeout_sec=max(2, min(int(raw.get("health_timeout_sec") or 8), 60)),
        remote_engine_port=max(1, min(int(raw.get("remote_engine_port") or 8091), 65535)),
        auto_restart_engine=bool(raw.get("auto_restart_engine", True)),
        auto_restart_bridge=bool(raw.get("auto_restart_bridge", False)),
    )
    if isinstance(excludes, list) and excludes:
        cfg.rsync_excludes = [str(x).strip() for x in excludes if str(x).strip()]
    return cfg


def availability() -> dict[str, Any]:
    cfg = get_config()
    if not cfg.enabled:
        return {
            "ok": False,
            "enabled": False,
            "detail": (
                "部署车道未开启。请打开 http://127.0.0.1:8000 → 配置中心 "
                "→「自动化部署」勾选开启并填写 SSH，保存后再试"
            ),
        }
    if cfg.provider != "local_ssh":
        return {
            "ok": False,
            "enabled": True,
            "detail": f"暂不支持 provider={cfg.provider}（MVP 仅 local_ssh）",
        }
    missing = []
    for key, val in (
        ("ssh_host", cfg.ssh_host),
        ("ssh_user", cfg.ssh_user),
        ("ssh_key_path", cfg.ssh_key_path),
        ("ssh_app_path", cfg.ssh_app_path),
    ):
        if not val:
            missing.append(key)
    if missing:
        return {
            "ok": False,
            "enabled": True,
            "detail": "SSH 配置不完整：" + "、".join(missing),
            "missing": missing,
        }
    errs = validate_ssh_settings(cfg)
    if errs:
        return {"ok": False, "enabled": True, "detail": errs[0], "errors": errs}
    return {
        "ok": True,
        "enabled": True,
        "detail": "部署车道就绪（按插件/单元增量 → 人确认 → SSH/rsync）",
        "provider": cfg.provider,
        "env_whitelist": list(cfg.env_whitelist),
        "default_env": cfg.default_env,
        "ssh_host": cfg.ssh_host,
        "ssh_app_path": cfg.ssh_app_path,
    }


def validate_ssh_settings(cfg: CodeDeployConfig) -> list[str]:
    errs: list[str] = []
    if not _HOST_OK.match(cfg.ssh_host or ""):
        errs.append("ssh_host 非法")
    if not _USER_OK.match(cfg.ssh_user or ""):
        errs.append("ssh_user 非法")
    key = (cfg.ssh_key_path or "").strip()
    if not key or not _SSH_KEY_OK.match(key.replace("~", "")):
        errs.append("ssh_key_path 非法")
    else:
        expanded = Path(key).expanduser()
        if not expanded.is_file():
            errs.append(f"私钥不存在：{expanded}")
        else:
            home = Path.home().resolve()
            try:
                expanded.resolve().relative_to(home)
            except ValueError:
                errs.append("私钥须位于用户 HOME 下（如 ~/.ssh）")
    app = (cfg.ssh_app_path or "").strip().rstrip("/")
    if not app or not _ABS_PATH_OK.match(app) or ".." in app:
        errs.append("ssh_app_path 须为绝对路径且不含 ..")
    elif app in {"/", "/home", "/root", "/www", "/var", "/opt", "/Users"}:
        errs.append("ssh_app_path 过浅，拒绝部署到系统根目录")
    return errs
