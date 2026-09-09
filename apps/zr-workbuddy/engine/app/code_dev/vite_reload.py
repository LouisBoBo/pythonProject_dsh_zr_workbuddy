"""同步后刷新本机 Vite：删除/改菜单后浏览器硬刷新即可，无需用户手动重启 npm run dev。

仅触碰 index.html 在 Vite 6 上常不够（外部写盘后模块图仍持有已删路由）。
对删除类与壳文件变更：若检测到本机 Vite 在跑，则按端口软重启（对齐目标工程 pull-refresh.sh）。
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_VITE_CONFIG_NAMES = ("vite.config.js", "vite.config.ts", "vite.config.mjs", "vite.config.cjs")
_FRONTEND_MARKERS = (
    "frontend/src/layouts/",
    "frontend/src/router/",
    "frontend/src/views/",
    "frontend/src/api/",
    "frontend/src/components/",
    "frontend/index.html",
    "src/layouts/",
    "src/router/",
    "src/views/",
)
_DEFAULT_PORT = 5175


def resolve_vite_frontend_root(target_root: Path | str) -> Path | None:
    """定位含 vite.config.* 的前端根（常见 frontend/ 或仓根）。"""
    root = Path(target_root).resolve()
    for cand in (root / "frontend", root):
        if not cand.is_dir():
            continue
        if any((cand / name).is_file() for name in _VITE_CONFIG_NAMES):
            return cand
    return None


def read_vite_dev_port(frontend: Path) -> int:
    """从 vite.config.* 读 server.port，缺省 5175。"""
    for name in _VITE_CONFIG_NAMES:
        p = frontend / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:8000]
        except OSError:
            continue
        m = re.search(r"port\s*:\s*(\d{2,5})", text)
        if m:
            try:
                port = int(m.group(1))
                if 1 <= port <= 65535:
                    return port
            except ValueError:
                pass
    return _DEFAULT_PORT


def _rels_need_nudge(synced_files: list[str] | None, deleted_files: list[str] | None) -> bool:
    for raw in list(synced_files or []) + list(deleted_files or []):
        rel = str(raw or "").replace("删除 ", "").replace("\\", "/").strip().lstrip("./")
        if not rel:
            continue
        if any(rel.startswith(m) or rel == m.rstrip("/") for m in _FRONTEND_MARKERS):
            return True
        if rel.endswith((".vue", ".jsx", ".tsx")) and "/src/" in f"/{rel}":
            return True
    return False


def _touch(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        now = time.time()
        os.utime(path, (now, now))
        return True
    except OSError:
        return False


def _clear_vite_cache(frontend: Path) -> bool:
    cache = frontend / "node_modules" / ".vite"
    if not cache.exists():
        return False
    try:
        shutil.rmtree(cache, ignore_errors=True)
        return not cache.exists()
    except OSError:
        return False


def _pids_listening_on_port(port: int) -> list[int]:
    """本机 TCP LISTEN 占用该端口的 PID（仅查询，不杀无关进程）。"""
    try:
        out = subprocess.check_output(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid_file(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return int(raw.split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _vite_seems_running(target_root: Path, port: int) -> bool:
    if _pids_listening_on_port(port):
        return True
    pid_file = Path(target_root).resolve() / ".dev-logs" / "frontend.pid"
    pid = _read_pid_file(pid_file)
    return bool(pid and _pid_alive(pid))


def _kill_pids(pids: list[int]) -> list[int]:
    killed: list[int] = []
    for pid in sorted(set(pids)):
        if not _pid_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except OSError:
            continue
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not any(_pid_alive(p) for p in killed):
            break
        time.sleep(0.1)
    for pid in killed:
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    return killed


def _wait_http_ready(port: int, *, timeout_sec: float = 15.0) -> bool:
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if 200 <= int(getattr(resp, "status", 200) or 200) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.35)
    return False


def soft_restart_vite(target_root: Path | str, frontend: Path) -> dict[str, Any]:
    """软重启本机 Vite：杀端口监听 → 清缓存 → nohup npm run dev → 等就绪。"""
    root = Path(target_root).resolve()
    frontend = frontend.resolve()
    port = read_vite_dev_port(frontend)
    log_dir = root / ".dev-logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "detail": f"无法创建 .dev-logs：{exc}", "port": port}

    pids = _pids_listening_on_port(port)
    pid_file = log_dir / "frontend.pid"
    old_pid = _read_pid_file(pid_file)
    if old_pid and _pid_alive(old_pid):
        pids.append(old_pid)
    killed = _kill_pids(pids)
    # 再扫一次端口，避免僵尸监听
    killed.extend(_kill_pids(_pids_listening_on_port(port)))
    time.sleep(0.4)

    _clear_vite_cache(frontend)

    log_path = log_dir / "frontend.log"
    try:
        log_f = open(log_path, "ab", buffering=0)
    except OSError as exc:
        return {"ok": False, "detail": f"无法写 frontend.log：{exc}", "port": port, "killed": killed}

    try:
        proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(frontend),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except OSError as exc:
        try:
            log_f.close()
        except OSError:
            pass
        return {"ok": False, "detail": f"无法启动 npm run dev：{exc}", "port": port, "killed": killed}

    try:
        pid_file.write_text(str(proc.pid) + "\n", encoding="utf-8")
    except OSError:
        pass

    ready = _wait_http_ready(port)
    detail = (
        f"软重启 Vite :{port}（killed={killed or '无'}；pid={proc.pid}；"
        + ("就绪" if ready else "启动中，请稍后硬刷新")
        + "）"
    )
    return {
        "ok": True,
        "detail": detail,
        "port": port,
        "pid": proc.pid,
        "ready": ready,
        "killed": killed,
    }


def nudge_vite_after_sync(
    target_root: Path | str,
    *,
    synced_files: list[str] | None = None,
    deleted_files: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    同步落盘后调用。删除/壳文件变更时优先软重启 Vite；失败不阻断写码任务。

    force=True：删除类任务即使未检测到路径标记也尝试。
    """
    if not force and not _rels_need_nudge(synced_files, deleted_files):
        return {"ok": True, "skipped": True, "detail": "无需唤醒 Vite"}

    root = Path(target_root).resolve()
    frontend = resolve_vite_frontend_root(root)
    if frontend is None:
        return {"ok": True, "skipped": True, "detail": "未检测到 Vite 前端工程"}

    actions: list[str] = []
    had_deletes = bool(deleted_files) or any(
        str(x).startswith("删除 ") for x in (synced_files or [])
    )
    need_restart = bool(force or had_deletes)
    if not need_restart:
        # 改菜单/路由也需要可靠刷新
        for raw in list(synced_files or []) + list(deleted_files or []):
            rel = str(raw or "").replace("删除 ", "").replace("\\", "/").strip()
            if "layouts/" in rel or "router/" in rel:
                need_restart = True
                break

    port = read_vite_dev_port(frontend)
    if need_restart and _vite_seems_running(root, port):
        restarted = soft_restart_vite(root, frontend)
        actions.append(str(restarted.get("detail") or "soft_restart"))
        if restarted.get("ok"):
            return {
                "ok": True,
                "skipped": False,
                "restarted": True,
                "ready": bool(restarted.get("ready")),
                "detail": "；".join(actions[:6]),
                "frontend": str(frontend),
                "port": port,
            }
        actions.append("软重启失败，回退触碰入口")

    if had_deletes or force:
        if _clear_vite_cache(frontend):
            actions.append("cleared node_modules/.vite")

    for raw in list(synced_files or []) + list(deleted_files or []):
        rel = str(raw or "").replace("删除 ", "").replace("\\", "/").strip().lstrip("./")
        if not rel or rel.startswith("删除"):
            continue
        p = root / rel
        if p.is_file() and _touch(p):
            actions.append(f"utime {rel}")

    index_html = frontend / "index.html"
    if _touch(index_html):
        actions.append("utime index.html")
    else:
        for name in ("src/main.js", "src/main.ts", "src/main.jsx", "src/main.tsx"):
            if _touch(frontend / name):
                actions.append(f"utime {name}")
                break

    if not actions:
        return {
            "ok": False,
            "skipped": False,
            "detail": "未能唤醒 Vite；若界面仍旧请确认前端 dev 是否在跑",
            "frontend": str(frontend),
        }
    return {
        "ok": True,
        "skipped": False,
        "restarted": False,
        "detail": "；".join(actions[:8]),
        "frontend": str(frontend),
        "port": port,
    }
