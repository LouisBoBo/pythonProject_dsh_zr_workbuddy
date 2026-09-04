"""本机 SSH + rsync：仅同步选定部署单元。"""
from __future__ import annotations

import ipaddress
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .config import CodeDeployConfig, validate_ssh_settings
from .units import DeployUnit

_REL_OK = re.compile(r"^[A-Za-z0-9_./\-]+$")


def _run(cmd: list[str], *, timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def _ssh_base(key: Path, port: int, user: str, host: str) -> list[str]:
    return [
        "ssh",
        "-i",
        str(key),
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=15",
        f"{user}@{host}",
    ]


def _rsync_ssh(key: Path, port: int) -> str:
    return (
        f"ssh -i {shlex.quote(str(key))} -p {port} "
        f"-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"
    )


def _exclude_args(cfg: CodeDeployConfig) -> list[str]:
    out: list[str] = []
    for pat in cfg.rsync_excludes or []:
        p = str(pat).strip()
        if p and re.match(r"^[A-Za-z0-9_.*?\[\]\-./]+$", p):
            out.extend(["--exclude", p])
    return out


def _safe_local_path(root: Path, rel: str) -> Path | None:
    """相对路径必须落在 workspace 内，拒绝绝对路径与 .. 逃逸。"""
    r = (rel or "").replace("\\", "/").strip()
    if not r or r.startswith("/") or r.startswith("~") or ".." in r.split("/"):
        return None
    if not _REL_OK.match(r):
        return None
    local = (root / r).resolve()
    try:
        local.relative_to(root.resolve())
    except ValueError:
        return None
    return local


def probe_remote_app(cfg: CodeDeployConfig) -> dict[str, Any]:
    """探测远端 ssh_app_path：是否存在、是否像空目录（影响强制全量）。"""
    errs = validate_ssh_settings(cfg)
    if errs:
        return {"ok": False, "empty": None, "error": errs[0]}
    key = Path(cfg.ssh_key_path).expanduser().resolve()
    app = (cfg.ssh_app_path or "").rstrip("/")
    ssh = _ssh_base(key, int(cfg.ssh_port), cfg.ssh_user, cfg.ssh_host)
    remote = (
        f"p={shlex.quote(app)}; "
        f"if [ ! -e \"$p\" ]; then echo missing; "
        f"elif [ -z \"$(ls -A \"$p\" 2>/dev/null)\" ]; then echo empty; "
        f"else echo ready; fi"
    )
    code, out, err = _run(ssh + [remote], timeout=40)
    token = (out or "").strip().splitlines()[-1] if (out or "").strip() else ""
    if code != 0:
        return {"ok": False, "empty": None, "error": (err or out or "SSH 探测失败")[:200]}
    if token in {"missing", "empty"}:
        return {"ok": True, "empty": True, "state": token, "error": ""}
    if token == "ready":
        return {"ok": True, "empty": False, "state": "ready", "error": ""}
    return {"ok": False, "empty": None, "error": f"远端探测未知输出：{token!r}"}


def deploy_units_ssh(
    workspace: Path | str,
    units: list[DeployUnit],
    cfg: CodeDeployConfig,
    *,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """按单元 rsync 到远端 ssh_app_path；按需重启引擎/DSH。"""
    def _log(msg: str) -> None:
        if log:
            log(msg)

    errs = validate_ssh_settings(cfg)
    if errs:
        return {"ok": False, "error": errs[0], "results": []}
    if not units:
        return {"ok": False, "error": "未选择任何部署单元", "results": []}

    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        return {"ok": False, "error": "工作区不存在", "results": []}
    key = Path(cfg.ssh_key_path).expanduser().resolve()
    app = cfg.ssh_app_path.rstrip("/")
    user, host, port = cfg.ssh_user, cfg.ssh_host, int(cfg.ssh_port)
    ssh = _ssh_base(key, port, user, host)
    rsh = _rsync_ssh(key, port)
    excludes = _exclude_args(cfg)
    results: list[dict[str, Any]] = []

    _log("SSH 登录探测 …")
    code, out, err = _run(ssh + ["echo ssh_ok"], timeout=40)
    if code != 0 or "ssh_ok" not in (out or ""):
        return {"ok": False, "error": f"SSH 失败：{(err or out or '').strip()[:300]}", "results": []}

    need_engine = False
    need_bridge = False

    for unit in units:
        urec: dict[str, Any] = {"id": unit.id, "ok": True, "logs": []}
        for rel in unit.local_rels:
            local = _safe_local_path(root, rel)
            if local is None:
                urec["ok"] = False
                urec["error"] = f"非法本地相对路径：{rel}"
                urec["logs"].append(urec["error"])
                break
            if not local.exists():
                urec["ok"] = False
                urec["error"] = f"本地路径不存在：{rel}"
                urec["logs"].append(urec["error"])
                break
            remote_parent = f"{app}/{Path(rel).parent.as_posix()}".rstrip("/")
            if Path(rel).parent.as_posix() in (".", ""):
                remote_parent = app
            remote_target = f"{user}@{host}:{app}/{rel}"
            if local.is_dir():
                remote_target = f"{user}@{host}:{app}/{rel}/"
            _log(f"rsync {rel} → 远端 …")
            urec["logs"].append(f"rsync {rel}")
            mkdir_target = remote_parent if local.is_file() else f"{app}/{rel}"
            mkdir_cmd = f"mkdir -p -- {shlex.quote(mkdir_target)}"
            _run(ssh + [mkdir_cmd], timeout=40)
            cmd = ["rsync", "-az", "--delete", "-e", rsh, *excludes]
            if local.is_dir():
                cmd.append(f"{local}/")
            else:
                cmd.append(str(local))
            cmd.append(remote_target)
            c2, o2, e2 = _run(cmd, timeout=300)
            if c2 != 0:
                urec["ok"] = False
                urec["error"] = (e2 or o2 or "rsync 失败")[:400]
                urec["logs"].append(urec["error"])
                break
        if urec["ok"]:
            if unit.action == "sync_engine_restart":
                need_engine = True
            elif unit.action in {"sync_bridge", "sync_bridge_reinstall"}:
                # 共享机默认只 rsync bridge 文件，绝不自动重装/重启 DSH
                if getattr(cfg, "auto_restart_bridge", False):
                    need_bridge = True
                else:
                    urec["logs"].append(
                        "已同步 bridge；跳过 DSH 重装（auto_restart_bridge=false）"
                    )
                    # 对外展示用：本单元实际动作为仅同步
                    urec["action_effective"] = "sync_bridge"
        results.append(urec)
        if not urec["ok"]:
            return {"ok": False, "error": f"单元 {unit.id} 失败：{urec.get('error')}", "results": results}

    # 远端运行时隔离：专用端口 + venv，禁止抢占/误杀已有服务
    prep = _ensure_remote_engine_runtime(ssh, app, cfg, log=_log)
    if not prep.get("ok"):
        return {
            "ok": False,
            "error": prep.get("error") or "远端运行时准备失败",
            "results": results,
            "engine_restart": False,
        }
    results.append({"id": "_remote_runtime", "ok": True, "logs": prep.get("logs") or []})

    if need_engine and getattr(cfg, "auto_restart_engine", True):
        remote = f"cd {shlex.quote(app)} && scripts/engine.sh zr-workbuddy restart"
        _log(f"远端重启本应用引擎（端口 {prep.get('port')}，不影响其它服务）…")
        c3, o3, e3 = _run(ssh + [f"bash -lc {shlex.quote(remote)}"], timeout=240)
        if c3 != 0:
            return {
                "ok": False,
                "error": f"引擎重启失败：{(e3 or o3)[:400]}",
                "results": results,
                "engine_restart": False,
            }
        results.append({"id": "_engine_restart", "ok": True, "logs": ["engine restart ok"]})
    elif need_engine:
        _log("已同步引擎文件；按配置跳过远端引擎重启（auto_restart_engine=false）")
        results.append({"id": "_engine_restart", "ok": True, "logs": ["skipped by config"]})

    if need_bridge and getattr(cfg, "auto_restart_bridge", False):
        # 二次保险：远端没有完整 DSH profile 时禁止 install（避免半残 .dsh / 误伤）
        prof_check = (
            "test -f \"$HOME/.dsh/profiles/web/package.json\" "
            "&& echo dsh_ok || echo dsh_missing"
        )
        _c_p, o_p, _e_p = _run(ssh + [prof_check], timeout=30)
        if "dsh_ok" not in (o_p or ""):
            return {
                "ok": False,
                "error": (
                    "已拒绝远端 bridge 重装：未找到 "
                    "~/.dsh/profiles/web/package.json。"
                    "共享机请保持 auto_restart_bridge=false，只同步文件+重启本应用引擎。"
                ),
                "results": results,
                "bridge_restart": False,
            }
        remote = (
            f"cd {shlex.quote(app)} && "
            "scripts/plugin.sh --app zr-workbuddy install bridge --restart"
        )
        _log("远端重装 bridge / 重启 DSH …")
        c4, o4, e4 = _run(ssh + [f"bash -lc {shlex.quote(remote)}"], timeout=300)
        if c4 != 0:
            return {
                "ok": False,
                "error": f"bridge 重装失败：{(e4 or o4)[:300]}",
                "results": results,
                "bridge_restart": False,
            }
        results.append({"id": "_bridge_restart", "ok": True, "logs": ["bridge reinstall ok"]})
    elif need_bridge:
        _log(
            "已同步 bridge 文件；共享机默认不重启 DSH（auto_restart_bridge=false），"
            "以免影响其它服务"
        )
        results.append({"id": "_bridge_restart", "ok": True, "logs": ["skipped by config"]})

    health: dict[str, Any] | None = None
    if (cfg.health_url or "").strip():
        health = probe_health(cfg.health_url, timeout=cfg.health_timeout_sec)
        _log(f"探活 {cfg.health_url} → {health}")

    return {
        "ok": True,
        "error": "",
        "results": results,
        "engine_restart": bool(need_engine and getattr(cfg, "auto_restart_engine", True)),
        "bridge_restart": bool(need_bridge and getattr(cfg, "auto_restart_bridge", False)),
        "health": health,
        "units": [u.id for u in units],
        "remote_engine_port": prep.get("port"),
    }


def _resolve_remote_port(cfg: CodeDeployConfig) -> int:
    """远端引擎监听端口：只认 remote_engine_port，绝不从 health_url 偷端口。

    health_url 常为公网 nginx（如 :8092），与引擎回环 :8091 不是同一端口；
    若用 health_url 覆盖，会误判「nginx 占用引擎端口」并拒绝部署。
    """
    port = int(getattr(cfg, "remote_engine_port", None) or 8091)
    # 保留口 / 公网反代口：禁止当作引擎监听
    if port in {80, 443, 22, 3306, 8000, 8009, 8092, 888, 8888}:
        return 8091
    if port < 1 or port > 65535:
        return 8091
    return port


def _ensure_remote_engine_runtime(
    ssh: list[str],
    app: str,
    cfg: CodeDeployConfig,
    *,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """在远端准备独立 runtime.yaml + venv；不触碰其它项目目录与端口。"""

    def _log(msg: str) -> None:
        if log:
            log(msg)

    port = _resolve_remote_port(cfg)
    logs: list[str] = []
    eng = f"{app.rstrip('/')}/apps/zr-workbuddy/engine"
    venv_py = f"{eng}/.venv/bin/python"
    req = f"{eng}/requirements.txt"
    runtime = f"{eng}/config/runtime.yaml"

    runtime_body = (
        "# 远端专用（由 code-deploy 生成，勿与本机 8000 混用）\n"
        "server:\n"
        "  host: 127.0.0.1\n"
        f"  port: {port}\n"
        f"python: {eng}/.venv/bin/python\n"
    )
    write_rt = (
        f"mkdir -p {shlex.quote(eng + '/config')} {shlex.quote(eng + '/data')} && "
        f"cat > {shlex.quote(runtime)} <<'EOF'\n{runtime_body}EOF"
    )
    _log(f"写入远端 runtime.yaml → 127.0.0.1:{port}")
    c1, o1, e1 = _run(ssh + [write_rt], timeout=40)
    if c1 != 0:
        return {"ok": False, "error": f"写 runtime 失败：{(e1 or o1)[:200]}", "logs": logs}
    logs.append(f"runtime port={port}")

    precheck = (
        f"pid=$(lsof -tiTCP:{port} -sTCP:LISTEN 2>/dev/null | head -1); "
        f"if [ -n \"$pid\" ]; then cmd=$(ps -p \"$pid\" -o args= 2>/dev/null || true); "
        f"case \"$cmd\" in *\"{eng}\"*|*\"/apps/zr-workbuddy/engine\"*) echo ours ;; "
        f"*) echo foreign:$pid:$cmd ;; esac; else echo free; fi"
    )
    c2, o2, _e2 = _run(ssh + [precheck], timeout=40)
    token = (o2 or "").strip().splitlines()[-1] if (o2 or "").strip() else ""
    if token.startswith("foreign:"):
        return {
            "ok": False,
            "error": (
                f"远端端口 {port} 已被其它服务占用（{token}）。"
                "请改 code_deploy.remote_engine_port / health_url，禁止抢占。"
            ),
            "logs": logs,
        }
    logs.append(f"port precheck={token or 'unknown'}")

    setup = (
        f"set -e; "
        f"if [ ! -x {shlex.quote(venv_py)} ]; then "
        f"python3 -m venv {shlex.quote(eng + '/.venv')}; fi; "
        f"{shlex.quote(venv_py)} -m pip install -q -U pip; "
        f"if [ -f {shlex.quote(req)} ]; then "
        f"{shlex.quote(venv_py)} -m pip install -q -r {shlex.quote(req)}; fi; "
        f"{shlex.quote(venv_py)} -c 'import fastapi,uvicorn'"
    )
    _log("远端准备独立 .venv 并安装依赖 …")
    c3, o3, e3 = _run(ssh + [f"bash -lc {shlex.quote(setup)}"], timeout=600)
    if c3 != 0:
        return {
            "ok": False,
            "error": f"远端 venv/依赖失败：{(e3 or o3)[:400]}",
            "logs": logs,
        }
    logs.append("venv ok")
    return {"ok": True, "port": port, "logs": logs, "error": ""}


def _is_blocked_health_host(host: str) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return True
    if h in {"localhost", "metadata.google.internal"}:
        return True
    if h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return bool(
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
    )


def probe_health(url: str, *, timeout: int = 8) -> dict[str, Any]:
    import urllib.request

    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return {"ok": False, "detail": "health_url 须为 http(s)"}
    try:
        parsed = urlparse(u)
    except Exception:  # noqa: BLE001
        return {"ok": False, "detail": "health_url 无法解析", "url": u}
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {"ok": False, "detail": "health_url 非法", "url": u}
    if _is_blocked_health_host(parsed.hostname):
        return {"ok": False, "detail": "health_url 禁止指向本机/链路本地/元数据地址", "url": u}
    try:
        req = urllib.request.Request(u, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            return {"ok": 200 <= int(code) < 400, "status": int(code), "url": u}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": str(e)[:200], "url": u}
