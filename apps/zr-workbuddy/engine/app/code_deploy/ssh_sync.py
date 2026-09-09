"""本机 SSH + rsync：仅同步选定部署单元。"""
from __future__ import annotations

import ipaddress
import json
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import CodeDeployConfig, validate_remote_restart_cmd, validate_ssh_settings
from .units import DeployUnit, is_vite_backend_layout

_REL_OK = re.compile(r"^[A-Za-z0-9_./\-]+$")
_UNIT_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,80}\.service$")
_SUPERVISOR_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
_MAX_HTTP_BODY = 2_000_000
_BACKEND_KEEP = (
    ".venv",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.db-journal",
    "*.db-wal",
    "*.db-shm",
    "uploads",
    "storage",
)
_ROUTER_PREFIX_RE = re.compile(
    r"APIRouter\s*\((?:[^)]*?prefix\s*=\s*[\"']([^\"']+)[\"'])"
)
_ROUTER_ROUTE_RE = re.compile(
    r"@router\.(?:get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"
)
_APP_ROUTE_RE = re.compile(
    r"@app\.(?:get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"
)


def _run(cmd: list[str], *, timeout: int = 120, cwd: str | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def _which_npm() -> str:
    found = shutil.which("npm")
    if found:
        return found
    home = Path.home()
    matches = sorted(home.glob(".nvm/versions/node/v*/bin/npm"), reverse=True)
    for cand in matches:
        if cand.is_file():
            return str(cand)
    return ""


def collect_local_api_paths(backend: Path | str) -> list[str]:
    """从本机 backend 源码收集 FastAPI 路径，用于部署后核对远端是否已加载新路由。"""
    root = Path(backend)
    app_dir = root / "app" if (root / "app").is_dir() else root
    found: list[str] = []
    seen: set[str] = set()
    if not app_dir.is_dir():
        return []
    for py in sorted(app_dir.rglob("*.py")):
        if any(part in {".venv", "venv", "__pycache__", "tests"} for part in py.parts):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        prefixes = _ROUTER_PREFIX_RE.findall(text)
        prefix = prefixes[0].rstrip("/") if prefixes else ""
        for rel in _ROUTER_ROUTE_RE.findall(text):
            rel_n = (rel or "").strip()
            if not rel_n:
                continue
            full = f"{prefix}/{rel_n.lstrip('/')}" if prefix else rel_n
            if not full.startswith("/"):
                full = "/" + full
            full = re.sub(r"/{2,}", "/", full)
            if full not in seen:
                seen.add(full)
                found.append(full)
        for rel in _APP_ROUTE_RE.findall(text):
            rel_n = (rel or "").strip()
            if not rel_n.startswith("/"):
                continue
            if rel_n not in seen:
                seen.add(rel_n)
                found.append(rel_n)
    return found


def parse_discovered_services(stdout: str) -> tuple[list[str], list[str]]:
    """解析远端探测输出：UNIT:foo.service / SUPERVISOR:name。"""
    units: list[str] = []
    supers: list[str] = []
    seen_u: set[str] = set()
    seen_s: set[str] = set()
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if line.startswith("UNIT:"):
            name = line[5:].strip()
            if _UNIT_NAME_OK.match(name) and name not in seen_u:
                seen_u.add(name)
                units.append(name)
        elif line.startswith("SUPERVISOR:"):
            name = line[11:].strip()
            if _SUPERVISOR_NAME_OK.match(name) and name not in seen_s:
                seen_s.add(name)
                supers.append(name)
    return units, supers


def entry_join(entry: str, path: str) -> str:
    base = (entry or "").strip().rstrip("/")
    p = path if path.startswith("/") else "/" + path
    return base + p if base else ""


def _app_path_safe_for_discover(app: str) -> bool:
    parts = [p for p in Path(app).parts if p not in {"/", ""}]
    return len(parts) >= 3


class _NoRedirect(HTTPRedirectHandler):
    """禁止跟随跳转，避免 health/openapi 被 302 到回环/元数据。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _http_get(url: str, *, timeout: int = 8) -> tuple[int, bytes]:
    opener = build_opener(_NoRedirect)
    req = Request(url, method="GET")
    with opener.open(req, timeout=timeout) as resp:
        code = int(getattr(resp, "status", None) or resp.getcode() or 0)
        raw = resp.read(_MAX_HTTP_BODY + 1)
    if len(raw) > _MAX_HTTP_BODY:
        raise ValueError("响应体过大")
    return code, raw


def _fetch_json(url: str, *, timeout: int = 8) -> dict[str, Any] | None:
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(u)
    except Exception:  # noqa: BLE001
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if _is_blocked_health_host(parsed.hostname):
        return None
    try:
        code, raw = _http_get(u, timeout=timeout)
        if not (200 <= code < 300):
            return None
        data = json.loads(raw.decode("utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _discover_backend_services_cmd(app: str) -> str:
    # 必须匹配 "$APP/"，避免 /www/wwwroot/zr 误配 zr-aicoding
    return (
        "APP=" + shlex.quote(app) + "\n"
        "for f in /etc/systemd/system/*.service; do\n"
        "  [ -f \"$f\" ] || continue\n"
        "  if grep -qF \"$APP/\" \"$f\"; then echo \"UNIT:$(basename \"$f\")\"; fi\n"
        "done\n"
        "for d in /etc/supervisor/conf.d /etc/supervisord.d; do\n"
        "  [ -d \"$d\" ] || continue\n"
        "  for f in \"$d\"/*; do\n"
        "    [ -f \"$f\" ] || continue\n"
        "    if grep -qF \"$APP/\" \"$f\"; then\n"
        "      n=$(grep -E '^\\[program:' \"$f\" | head -1 | sed 's/\\[program://;s/\\]//')\n"
        "      [ -n \"$n\" ] && echo \"SUPERVISOR:$n\"\n"
        "    fi\n"
        "  done\n"
        "done\n"
        "echo DISCOVER_DONE\n"
    )


def _install_remote_backend_deps(
    ssh: list[str],
    app: str,
    log: Callable[[str], None],
    urec: dict[str, Any],
) -> bool:
    """在远端 backend/.venv 里按 requirements.txt 安装（有 venv 才执行）。"""
    remote = (
        "APP=" + shlex.quote(app) + "\n"
        "REQ=\"$APP/backend/requirements.txt\"\n"
        "PIP=\"$APP/backend/.venv/bin/pip\"\n"
        "if [ ! -f \"$REQ\" ]; then echo pip_skip_no_req; exit 0; fi\n"
        "if [ ! -x \"$PIP\" ]; then echo pip_skip_no_venv; exit 0; fi\n"
        "\"$PIP\" install -r \"$REQ\" -q && echo pip_ok\n"
    )
    log("远端安装 backend 依赖 …")
    urec["logs"].append("pip install -r backend/requirements.txt")
    code, out, err = _run(ssh + [f"bash -lc {shlex.quote(remote)}"], timeout=180)
    token = (out or "").strip().splitlines()[-1] if (out or "").strip() else ""
    if code != 0 or token not in {"pip_ok", "pip_skip_no_req", "pip_skip_no_venv"}:
        urec["ok"] = False
        urec["error"] = (err or out or "远端 pip install 失败")[:400]
        urec["logs"].append(urec["error"])
        return False
    urec["logs"].append(token)
    return True


def _restart_and_verify_backend(
    ssh: list[str],
    *,
    cfg: CodeDeployConfig,
    app: str,
    backend: Path,
    log: Callable[[str], None],
    urec: dict[str, Any],
) -> bool:
    """同步后必须让远端 API 进程加载新代码；仅 rsync 不够（uvicorn 无 --reload）。"""
    custom = str(getattr(cfg, "remote_restart_cmd", "") or "").strip()
    if custom:
        cmd_err = validate_remote_restart_cmd(custom)
        if cmd_err:
            urec["ok"] = False
            urec["error"] = cmd_err
            urec["logs"].append(cmd_err)
            return False
        log("执行配置的远端重启命令 …")
        urec["logs"].append("remote_restart_cmd")
        c3, o3, e3 = _run(ssh + [f"bash -lc {shlex.quote(custom)}"], timeout=120)
        if c3 != 0:
            urec["ok"] = False
            urec["error"] = (e3 or o3 or "远端重启失败")[:400]
            urec["logs"].append(urec["error"])
            return False
        urec["logs"].append("remote restart ok")
    else:
        if not _app_path_safe_for_discover(app):
            urec["ok"] = False
            urec["error"] = (
                "后端已同步，但远端目录过浅，无法自动匹配 systemd。"
                "请在设置填写「远端重启命令」，例如 systemctl restart zr-aicoding-api"
            )
            urec["logs"].append(urec["error"])
            return False
        log("探测并重启远端 API 进程 …")
        urec["logs"].append("discover systemd/supervisor")
        c0, o0, e0 = _run(
            ssh + [f"bash -lc {shlex.quote(_discover_backend_services_cmd(app))}"],
            timeout=40,
        )
        if c0 != 0 or "DISCOVER_DONE" not in (o0 or ""):
            urec["ok"] = False
            urec["error"] = (e0 or o0 or "探测远端 API 服务失败")[:400]
            urec["logs"].append(urec["error"])
            return False
        units, supers = parse_discovered_services(o0 or "")
        if len(units) > 3:
            urec["ok"] = False
            urec["error"] = (
                f"匹配到过多 systemd 服务（{len(units)}），已中止以免误重启。"
                "请在设置填写明确的「远端重启命令」"
            )
            urec["logs"].append(urec["error"])
            return False
        if units:
            for unit in units:
                log(f"systemctl restart {unit} …")
                urec["logs"].append(f"systemctl restart {unit}")
                c1, o1, e1 = _run(
                    ssh + [f"bash -lc {shlex.quote('systemctl restart ' + shlex.quote(unit))}"],
                    timeout=60,
                )
                if c1 != 0:
                    urec["ok"] = False
                    urec["error"] = (e1 or o1 or f"重启 {unit} 失败")[:400]
                    urec["logs"].append(urec["error"])
                    return False
            urec["logs"].append("remote restart ok")
        elif supers:
            for name in supers[:3]:
                log(f"supervisorctl restart {name} …")
                urec["logs"].append(f"supervisorctl restart {name}")
                c1, o1, e1 = _run(
                    ssh
                    + [
                        f"bash -lc {shlex.quote('supervisorctl restart ' + shlex.quote(name))}"
                    ],
                    timeout=60,
                )
                if c1 != 0:
                    urec["ok"] = False
                    urec["error"] = (e1 or o1 or f"重启 supervisor {name} 失败")[:400]
                    urec["logs"].append(urec["error"])
                    return False
            urec["logs"].append("remote restart ok")
        else:
            urec["ok"] = False
            urec["error"] = (
                "后端文件已同步，但找不到匹配该目录的 systemd/supervisor 服务，"
                "API 进程不会加载新接口。请在设置填写「远端重启命令」，"
                "例如 systemctl restart zr-aicoding-api"
            )
            urec["logs"].append(urec["error"])
            return False

    entry = ""
    if hasattr(cfg, "resolve_entry_url"):
        entry = cfg.resolve_entry_url()
    else:
        entry = (getattr(cfg, "entry_url", None) or cfg.health_url or "").strip()
    api_health = entry_join(entry, "/api/health")
    if api_health:
        log(f"探活 API {api_health} …")
        last: dict[str, Any] = {}
        for _ in range(15):
            last = probe_health(api_health, timeout=min(4, int(cfg.health_timeout_sec or 8)))
            if last.get("ok"):
                break
            time.sleep(1)
        if not last.get("ok"):
            urec["ok"] = False
            urec["error"] = (
                "已重启 API，但 /api/health 未就绪："
                + str(last.get("detail") or last.get("status") or "timeout")[:200]
            )
            urec["logs"].append(urec["error"])
            return False
        urec["logs"].append("api health ok")

    openapi_url = entry_join(entry, "/openapi.json")
    local_paths = [
        p
        for p in collect_local_api_paths(backend)
        if p.startswith("/api/") and p.count("/") >= 2
    ][:40]
    if openapi_url and local_paths:
        spec = None
        for _ in range(8):
            spec = _fetch_json(openapi_url, timeout=8)
            if spec and isinstance(spec.get("paths"), dict):
                break
            time.sleep(1)
        if spec and isinstance(spec.get("paths"), dict):
            remote_paths = {str(x) for x in spec["paths"].keys()}
            missing = [p for p in local_paths if p not in remote_paths]
            if missing:
                urec["ok"] = False
                urec["error"] = (
                    "远端 API 仍未加载新路由（典型原因：进程没真正重启）。缺："
                    + "、".join(missing[:5])
                )
                urec["logs"].append(urec["error"])
                return False
            urec["logs"].append("openapi routes ok")
        else:
            urec["ok"] = False
            urec["error"] = (
                "无法读取远端 /openapi.json，不能确认 API 已加载新路由。"
                "请检查 nginx 是否反代了 /openapi.json 与 /api/"
            )
            urec["logs"].append(urec["error"])
            return False
    return True


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


def _sync_vite_backend_layout(
    root: Path,
    *,
    cfg: CodeDeployConfig,
    user: str,
    host: str,
    app: str,
    rsh: str,
    ssh: list[str],
    excludes: list[str],
    log: Callable[[str], None],
) -> dict[str, Any]:
    """对齐 GitHub deploy-staging：本机 npm run build，再 rsync dist + backend。"""
    urec: dict[str, Any] = {"id": "workspace", "ok": True, "logs": []}
    npm = _which_npm()
    if not npm:
        urec["ok"] = False
        urec["error"] = "本机找不到 npm，无法构建前端 dist（8090 跑的是构建产物不是源码）"
        urec["logs"].append(urec["error"])
        return urec
    frontend = root / "frontend"
    log("本机构建前端 npm run build …")
    urec["logs"].append("npm run build")
    c0, o0, e0 = _run([npm, "run", "build"], timeout=420, cwd=str(frontend))
    if c0 != 0:
        urec["ok"] = False
        urec["error"] = (e0 or o0 or "npm run build 失败")[:400]
        urec["logs"].append(urec["error"])
        return urec
    dist = frontend / "dist"
    if not dist.is_dir():
        urec["ok"] = False
        urec["error"] = "构建完成但没有 frontend/dist，无法更新预发页面"
        urec["logs"].append(urec["error"])
        return urec
    backend = root / "backend"
    mkdir_cmd = (
        f"mkdir -p -- {shlex.quote(app + '/frontend/dist')} "
        f"{shlex.quote(app + '/backend')}"
    )
    _run(ssh + [mkdir_cmd], timeout=40)

    log("rsync frontend/dist → 远端 …")
    urec["logs"].append("rsync frontend/dist")
    cmd_fe = [
        "rsync",
        "-az",
        "--delete",
        "-e",
        rsh,
        f"{dist}/",
        f"{user}@{host}:{app}/frontend/dist/",
    ]
    c1, o1, e1 = _run(cmd_fe, timeout=300)
    if c1 != 0:
        urec["ok"] = False
        urec["error"] = (e1 or o1 or "rsync frontend/dist 失败")[:400]
        urec["logs"].append(urec["error"])
        return urec

    log("rsync backend → 远端 …")
    urec["logs"].append("rsync backend")
    cmd_be = [
        "rsync",
        "-az",
        "--delete",
        "-e",
        rsh,
        *excludes,
    ]
    for pat in _BACKEND_KEEP:
        cmd_be.extend(["--exclude", pat])
    cmd_be.extend(
        [
            f"{backend}/",
            f"{user}@{host}:{app}/backend/",
        ]
    )
    c2, o2, e2 = _run(cmd_be, timeout=300)
    if c2 != 0:
        urec["ok"] = False
        urec["error"] = (e2 or o2 or "rsync backend 失败")[:400]
        urec["logs"].append(urec["error"])
        return urec
    if not _install_remote_backend_deps(ssh, app, log, urec):
        return urec
    if not _restart_and_verify_backend(
        ssh, cfg=cfg, app=app, backend=backend, log=log, urec=urec
    ):
        return urec
    return urec


def deploy_units_ssh(
    workspace: Path | str,
    units: list[DeployUnit],
    cfg: CodeDeployConfig,
    *,
    log: Callable[[str], None] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按单元 rsync 到远端 ssh_app_path；按需重启引擎/DSH。

    成功后在远端写入 last_deploy_receipt.json，便于服务器核对「本次实际同步了什么」。
    """
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
        if unit.id == "workspace" and is_vite_backend_layout(root):
            urec = _sync_vite_backend_layout(
                root,
                cfg=cfg,
                user=user,
                host=host,
                app=app,
                rsh=rsh,
                ssh=ssh,
                excludes=excludes,
                log=_log,
            )
            results.append(urec)
            if not urec["ok"]:
                return {
                    "ok": False,
                    "error": f"单元 {unit.id} 失败：{urec.get('error')}",
                    "results": results,
                }
            continue
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
                # 默认仅同步；auto_restart_bridge=true 才重启远端宿主
                if getattr(cfg, "auto_restart_bridge", False):
                    need_bridge = True
                else:
                    urec["logs"].append(
                        "已同步 bridge；默认不重启远端宿主（auto_restart_bridge=false）"
                    )
                    urec["action_effective"] = "sync_bridge"
        results.append(urec)
        if not urec["ok"]:
            return {"ok": False, "error": f"单元 {unit.id} 失败：{urec.get('error')}", "results": results}

    unified = bool(getattr(cfg, "unified_product", True))
    want_engine_runtime = need_engine or unified
    prep: dict[str, Any] = {"ok": True, "port": None, "logs": []}
    if want_engine_runtime:
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
    else:
        _log("非一体部署且无引擎单元，跳过远端 WorkBuddy 引擎准备")

    engine_restarted = False
    engine_ensured = False

    # 引擎收尾：有 engine 单元则 restart；一体部署时无变更也 ensure 保活
    if need_engine and getattr(cfg, "auto_restart_engine", True):
        remote = f"cd {shlex.quote(app)} && scripts/engine.sh zr-workbuddy restart"
        _log(f"远端重启本应用引擎（端口 {prep.get('port')}）…")
        c3, o3, e3 = _run(ssh + [f"bash -lc {shlex.quote(remote)}"], timeout=240)
        if c3 != 0:
            return {
                "ok": False,
                "error": f"引擎重启失败：{(e3 or o3)[:400]}",
                "results": results,
                "engine_restart": False,
            }
        engine_restarted = True
        results.append({"id": "_engine_restart", "ok": True, "logs": ["engine restart ok"]})
    elif need_engine:
        _log("已同步引擎文件；按配置跳过远端引擎重启（auto_restart_engine=false）")
        results.append({"id": "_engine_restart", "ok": True, "logs": ["skipped by config"]})
    elif unified and getattr(cfg, "auto_restart_engine", True):
        remote = f"cd {shlex.quote(app)} && scripts/engine.sh zr-workbuddy ensure"
        _log(f"一体部署：确保远端引擎在跑（端口 {prep.get('port')}）…")
        c3, o3, e3 = _run(ssh + [f"bash -lc {shlex.quote(remote)}"], timeout=240)
        if c3 != 0:
            return {
                "ok": False,
                "error": f"引擎 ensure 失败：{(e3 or o3)[:400]}",
                "results": results,
                "engine_restart": False,
            }
        engine_ensured = True
        results.append({"id": "_engine_ensure", "ok": True, "logs": ["engine ensure ok"]})

    # 聊天壳收尾：一体部署每次确保；或 bridge 单元且 auto_restart_bridge
    want_host = unified or (
        need_bridge and getattr(cfg, "auto_restart_bridge", False)
    )
    force_host_restart = bool(
        need_bridge and getattr(cfg, "auto_restart_bridge", False)
    )
    bridge_restarted = False
    host_up = False
    if want_host:
        host_res = _ensure_remote_host_web(
            ssh,
            app,
            cfg,
            force_restart=force_host_restart,
            also_reinstall_bridge=bool(need_bridge and getattr(cfg, "auto_restart_bridge", False)),
            log=_log,
        )
        results.append(host_res)
        if not host_res.get("ok") and host_res.get("hard_fail"):
            return {
                "ok": False,
                "error": host_res.get("error") or "远端聊天壳收尾失败",
                "results": results,
                "bridge_restart": False,
                "host_up": False,
            }
        bridge_restarted = bool(host_res.get("bridge_restart"))
        host_up = bool(host_res.get("host_up"))
        if host_res.get("warning"):
            _log(str(host_res.get("warning")))
    elif need_bridge:
        _log("已同步 bridge 文件；按配置跳过远端宿主重启（auto_restart_bridge=false）")
        results.append({"id": "_bridge_restart", "ok": True, "logs": ["skipped by config"]})

    entry = ""
    if hasattr(cfg, "resolve_entry_url"):
        entry = cfg.resolve_entry_url()
    else:
        entry = (getattr(cfg, "entry_url", None) or cfg.health_url or "").strip()
    health: dict[str, Any] | None = None
    if entry:
        health = probe_health(entry, timeout=cfg.health_timeout_sec)
        _log(f"入口探活 {entry} → {health}")

    receipt = _write_remote_deploy_receipt(
        ssh,
        app,
        units=units,
        results=results,
        cfg=cfg,
        meta=meta or {},
        engine_restart=engine_restarted or engine_ensured,
        bridge_restart=bridge_restarted,
        remote_engine_port=prep.get("port"),
        health=health if isinstance(health, dict) else None,
        log=_log,
    )
    if receipt.get("ok"):
        results.append({"id": "_receipt", "ok": True, "logs": [receipt.get("path") or "receipt ok"]})
    else:
        # 回执失败不回滚已同步文件，但标进结果便于排查
        results.append(
            {
                "id": "_receipt",
                "ok": False,
                "logs": [receipt.get("error") or "receipt failed"],
            }
        )

    return {
        "ok": True,
        "error": "",
        "results": results,
        "engine_restart": engine_restarted,
        "engine_ensure": engine_ensured,
        "bridge_restart": bridge_restarted,
        "host_up": host_up,
        "unified_product": unified,
        "health": health,
        "entry_url": entry,
        "units": [u.id for u in units],
        "remote_engine_port": prep.get("port"),
        "remote_host_port": int(getattr(cfg, "remote_host_port", 3080) or 3080),
        "remote_receipt_path": receipt.get("path") or "",
        "remote_receipt_ok": bool(receipt.get("ok")),
    }


def _ensure_remote_host_web(
    ssh: list[str],
    app: str,
    cfg: CodeDeployConfig,
    *,
    force_restart: bool = False,
    also_reinstall_bridge: bool = False,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """一体收尾：确保远端聊天壳（dsh web）在跑；无 profile 时软跳过。"""

    def _log(msg: str) -> None:
        if log:
            log(msg)

    host_port = int(getattr(cfg, "remote_host_port", 3080) or 3080)
    logs: list[str] = []
    # 二次保险：远端没有完整 DSH profile 时不 install（避免半残 .dsh）
    prof_check = (
        "test -f \"$HOME/.dsh/profiles/web/package.json\" "
        "&& echo dsh_ok || echo dsh_missing"
    )
    _c_p, o_p, _e_p = _run(ssh + [prof_check], timeout=30)
    if "dsh_ok" not in (o_p or ""):
        warn = (
            "远端无 ~/.dsh/profiles/web/package.json，已跳过聊天壳启动；"
            "业务文件已同步。请在服务器安装 dsh 并用 scripts/host.sh wire 接线后再部署。"
        )
        _log(warn)
        return {
            "id": "_host_web",
            "ok": True,
            "hard_fail": False,
            "host_up": False,
            "bridge_restart": False,
            "logs": ["skipped: no remote DSH profile", warn],
            "warning": warn,
        }

    if also_reinstall_bridge:
        remote_install = (
            f"cd {shlex.quote(app)} && "
            "scripts/plugin.sh --app zr-workbuddy install bridge"
        )
        _log("远端重装 bridge …")
        c4, o4, e4 = _run(ssh + [f"bash -lc {shlex.quote(remote_install)}"], timeout=300)
        if c4 != 0:
            return {
                "id": "_host_web",
                "ok": False,
                "hard_fail": True,
                "host_up": False,
                "bridge_restart": False,
                "error": f"bridge 重装失败：{(e4 or o4)[:300]}",
                "logs": logs,
            }
        logs.append("bridge install ok")

    listen_check = (
        f"pid=$(lsof -tiTCP:{host_port} -sTCP:LISTEN 2>/dev/null | head -1); "
        f"if [ -n \"$pid\" ]; then echo up:$pid; else echo down; fi"
    )
    _c_l, o_l, _e_l = _run(ssh + [listen_check], timeout=30)
    token = (o_l or "").strip().splitlines()[-1] if (o_l or "").strip() else ""
    already_up = token.startswith("up:")
    if already_up and not force_restart:
        _log(f"远端聊天壳已在监听 :{host_port}，跳过重启")
        return {
            "id": "_host_web",
            "ok": True,
            "hard_fail": False,
            "host_up": True,
            "bridge_restart": False,
            "logs": logs + [f"already listening :{host_port}"],
        }

    remote_restart = (
        f"cd {shlex.quote(app)} && "
        f"DSH_WEB_PORT={host_port} nohup scripts/restart-dsh.sh "
        ">/tmp/zr-workbuddy-dsh-restart.log 2>&1 & "
        "echo dsh_restart_started"
    )
    _log(f"远端后台启动/重启聊天壳（:{host_port}）…")
    c5, o5, e5 = _run(ssh + [f"bash -lc {shlex.quote(remote_restart)}"], timeout=60)
    if c5 != 0 or "dsh_restart_started" not in (o5 or ""):
        return {
            "id": "_host_web",
            "ok": False,
            "hard_fail": True,
            "host_up": False,
            "bridge_restart": False,
            "error": (
                "启动远端聊天壳失败："
                f"{(e5 or o5)[:300]}；可 SSH 查看 /tmp/zr-workbuddy-dsh-restart.log"
            ),
            "logs": logs,
        }
    logs.append("host restart started (background)")
    return {
        "id": "_host_web",
        "ok": True,
        "hard_fail": False,
        "host_up": True,
        "bridge_restart": bool(also_reinstall_bridge or force_restart),
        "logs": logs,
    }


def _write_remote_deploy_receipt(
    ssh: list[str],
    app: str,
    *,
    units: list[DeployUnit],
    results: list[dict[str, Any]],
    cfg: CodeDeployConfig,
    meta: dict[str, Any],
    engine_restart: bool,
    bridge_restart: bool,
    remote_engine_port: Any,
    health: dict[str, Any] | None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """在远端落下本次实际同步回执（服务器可 cat 核对）。"""
    import json
    from datetime import datetime, timezone

    def _log(msg: str) -> None:
        if log:
            log(msg)

    synced_rels: list[str] = []
    unit_rows: list[dict[str, Any]] = []
    for u in units:
        rels = list(u.local_rels)
        synced_rels.extend(rels)
        unit_rows.append(
            {
                "id": u.id,
                "kind": u.kind,
                "action": u.action,
                "local_rels": rels,
            }
        )
    # 去重保序
    seen: set[str] = set()
    rels_unique: list[str] = []
    for r in synced_rels:
        if r not in seen:
            seen.add(r)
            rels_unique.append(r)

    mode = str(meta.get("mode") or "").strip() or "unknown"
    receipt = {
        "ok": True,
        "written_at": datetime.now(timezone.utc).isoformat(),
        "job_id": meta.get("job_id") or "",
        "env": meta.get("env") or cfg.default_env,
        "mode": mode,
        "mode_label": "全量" if mode == "full" else ("增量" if mode == "incremental" else mode),
        "head_sha": meta.get("head_sha") or "",
        "ssh_host": cfg.ssh_host,
        "ssh_app_path": app,
        "unit_ids": [u.id for u in units],
        "units": unit_rows,
        "synced_rels": rels_unique,
        "engine_restart": engine_restart,
        "bridge_restart": bridge_restart,
        "remote_engine_port": remote_engine_port,
        "unified_product": bool(getattr(cfg, "unified_product", True)),
        "entry_url": (
            cfg.resolve_entry_url()
            if hasattr(cfg, "resolve_entry_url")
            else (cfg.health_url or "").strip()
        ),
        "health_url": (
            cfg.resolve_entry_url()
            if hasattr(cfg, "resolve_entry_url")
            else (cfg.health_url or "").strip()
        ),
        "health": health,
        "rsync_results": [
            {"id": r.get("id"), "ok": r.get("ok"), "logs": (r.get("logs") or [])[:8]}
            for r in results
            if isinstance(r, dict) and not str(r.get("id") or "").startswith("_")
        ],
        "note": "本文件由 code-deploy 在远端写入；unit_ids/synced_rels 即本次实际 rsync 范围。",
    }
    unit_ids = {u.id for u in units}
    if "workspace" in unit_ids and "engine" not in unit_ids and "bridge" not in unit_ids:
        rel_path = ".workbuddy-deploy/last_deploy_receipt.json"
        remote_dir = f"{app.rstrip('/')}/.workbuddy-deploy"
    else:
        rel_path = "apps/zr-workbuddy/engine/data/code_deploy/last_deploy_receipt.json"
        remote_dir = f"{app.rstrip('/')}/apps/zr-workbuddy/engine/data/code_deploy"
    remote_path = f"{app.rstrip('/')}/{rel_path}"
    body = json.dumps(receipt, ensure_ascii=False, indent=2)
    _log(f"写入远端部署回执 → {remote_path}")

    # 本机写临时文件再 scp，避免 ssh python -c 引号被踩碎
    import tempfile

    key = Path(cfg.ssh_key_path).expanduser().resolve()
    user, host, port = cfg.ssh_user, cfg.ssh_host, int(cfg.ssh_port)
    tmp = ""
    c2, o2, e2 = 1, "", "scp 未执行"
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False
        ) as tf:
            tf.write(body)
            tmp = tf.name
        mkdir_c, _, mkdir_e = _run(
            ssh + [f"mkdir -p -- {shlex.quote(remote_dir)}"], timeout=30
        )
        if mkdir_c != 0:
            return {"ok": False, "error": f"建目录失败：{(mkdir_e or '')[:200]}", "path": remote_path}
        scp = [
            "scp",
            "-i",
            str(key),
            "-P",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=15",
            tmp,
            f"{user}@{host}:{remote_path}",
        ]
        c2, o2, e2 = _run(scp, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e), "path": remote_path}
    finally:
        if tmp:
            try:
                Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass
    if c2 != 0:
        return {
            "ok": False,
            "error": ((e2 or o2 or "scp 回执失败")[:300]),
            "path": remote_path,
        }
    return {"ok": True, "path": remote_path, "error": ""}



def _resolve_remote_port(cfg: CodeDeployConfig) -> int:
    """远端引擎监听端口：只认 remote_engine_port，绝不从 health_url 偷端口。

    health_url / entry_url 常为公网 nginx（如 :8093），与引擎回环不是同一端口；
    若用 URL 覆盖，会误判「nginx 占用引擎端口」并拒绝部署。
    """
    default = 8095
    port = int(getattr(cfg, "remote_engine_port", None) or default)
    # 保留口 / 公网反代口 / 旧项目引擎口：禁止当作本应用引擎监听
    if port in {80, 443, 22, 3306, 8000, 8009, 8091, 8092, 8093, 888, 8888}:
        return default
    if port < 1 or port > 65535:
        return default
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
        code, _raw = _http_get(u, timeout=timeout)
        return {"ok": 200 <= int(code) < 400, "status": int(code), "url": u}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": str(e)[:200], "url": u}
