#!/usr/bin/env python3
"""验收：公司/私有插件市场不得丢失。

失败条件（任一）：
- 合并目录 / 指定 DSHM_REGISTRY_URL 拉不到含 @zhongruan 的目录
- 运行中的 dsh 宿主进程未带 DSHM_REGISTRY_URL（会静默掉回官方市场）
- 目录缺少「中软」分类或 seed 里应有的公司包

环境：
  DSHM_REGISTRY_URL   优先验收该 URL（默认试 18731 / 18732 / 公司站）
  WORKBUDDY_WEB_PORT  用于找监听中的 dsh（默认 3081）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "apps" / "zr-workbuddy" / "config" / "company-dsh-plugins.seed.json"
USER_AGENT = "workbuddy-verify-company-market/1.0"


def _http_json(url: str, timeout: float = 3.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None


def _seed_names() -> list[str]:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    out: list[str] = []
    for p in data.get("plugins") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("npm") or p.get("name") or "").strip()
        if name.startswith("@zhongruan/"):
            out.append(name)
    return out


def _catalog_ok(data: dict, required: list[str]) -> tuple[bool, str]:
    plugins = data.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        return False, "plugins 为空"
    names = {
        str(p.get("npm") or p.get("name") or "")
        for p in plugins
        if isinstance(p, dict)
    }
    zhong = [n for n in names if n.startswith("@zhongruan/")]
    if len(zhong) < 1:
        return False, "目录中没有任何 @zhongruan/*（已掉回官方市场或合并失败）"
    cats = data.get("categories") or {}
    if isinstance(cats, dict) and "zhongruan" not in cats:
        # 合并目录必有；纯公司站可能没有该 key——只要有 @zhongruan 包仍算过
        if not any(n.startswith("@zhongruan/") for n in names):
            return False, "缺少 zhongruan 分类且无公司包"
    missing = [n for n in required if n not in names]
    if missing:
        return False, f"缺少 seed 公司包: {', '.join(missing)}"
    # 置顶：至少前 20 里要有公司包（防官方排序盖住）
    head = [
        str(p.get("npm") or p.get("name") or "")
        for p in plugins[:20]
        if isinstance(p, dict)
    ]
    if not any(n.startswith("@zhongruan/") for n in head):
        return False, "前 20 条没有 @zhongruan/*（未置顶，用户会以为中软丢了）"
    return True, f"公司包 {len(zhong)} 个，seed 齐全，前 20 含中软"


def _listener_pid(port: int) -> str | None:
    try:
        out = subprocess.check_output(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return out.splitlines()[0].strip() if out else None


def _process_has_dshm(pid: str) -> tuple[bool, str]:
    try:
        out = subprocess.check_output(["ps", "eww", "-p", pid], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        return False, f"无法读进程环境: {exc}"
    m = re.search(r"DSHM_REGISTRY_URL=([^\s]+)", out)
    if not m:
        return False, f"PID {pid} 未设置 DSHM_REGISTRY_URL（会静默用官方市场，中软插件「消失」）"
    url = m.group(1).strip()
    if not url:
        return False, f"PID {pid} 的 DSHM_REGISTRY_URL 为空（显式恢复官方市场）"
    if "awesome-dsh-plugin.com" in url and "127.0.0.1" not in url and "zhongruan" not in url:
        return False, f"PID {pid} 指向纯官方目录: {url}"
    return True, f"PID {pid} DSHM_REGISTRY_URL={url}"


def _home_env_locked(dsh_home: Path) -> tuple[bool, str]:
    """交付态要求 $DSH_HOME/.env 持久化块仍在（防裸 dsh / 更新市场后丢失）。"""
    if os.environ.get("WORKBUDDY_ALLOW_OFFICIAL_MARKET") == "1":
        return True, "破窗 WORKBUDDY_ALLOW_OFFICIAL_MARKET=1，跳过 .env 锁定检查"
    envf = dsh_home / ".env"
    if not envf.is_file():
        return False, f"缺少锁定文件 {envf}（应含 workbuddy-company-market 块）"
    text = envf.read_text(encoding="utf-8", errors="replace")
    if "# --- workbuddy-company-market ---" not in text:
        return False, f"{envf} 缺少 workbuddy-company-market 标记块"
    m = re.search(r"(?m)^DSHM_REGISTRY_URL=(\S+)\s*$", text)
    if not m or not m.group(1).strip():
        return False, f"{envf} 未持久化非空 DSHM_REGISTRY_URL"
    url = m.group(1).strip()
    if "awesome-dsh-plugin.com" in url and "127.0.0.1" not in url:
        return False, f"{envf} 指向纯官方目录: {url}"
    return True, f"{envf} 已锁定 DSHM_REGISTRY_URL={url}"


def main() -> int:
    required = _seed_names()
    if not required:
        print("错误: company-dsh-plugins.seed.json 无 @zhongruan 条目", file=sys.stderr)
        return 2

    candidates: list[str] = []
    env_url = os.environ.get("DSHM_REGISTRY_URL")
    if env_url:
        candidates.append(env_url)
    candidates.extend(
        [
            "http://127.0.0.1:18731/plugins.json",
            "http://127.0.0.1:18732/plugins.json",
            os.environ.get("COMPANY_DSH_MARKET_URL")
            or "http://175.178.238.31/dsh-plugins/plugins.json",
        ]
    )

    catalog_msg = ""
    catalog_ok = False
    used = ""
    for url in candidates:
        if not url:
            continue
        data = _http_json(url)
        if not data:
            continue
        ok, msg = _catalog_ok(data, required)
        used = url
        catalog_msg = msg
        catalog_ok = ok
        if ok:
            break

    errors: list[str] = []
    if not catalog_ok:
        errors.append(f"插件目录验收失败（试过 {candidates}）: {catalog_msg or '全部不可达'}")
    else:
        print(f"目录 OK ({used}): {catalog_msg}")

    dsh_home = Path(os.environ.get("DSH_HOME") or Path.home() / ".dsh").expanduser()
    ok_env, msg_env = _home_env_locked(dsh_home)
    print(("锁定 OK: " if ok_env else "锁定失败: ") + msg_env)
    if not ok_env:
        errors.append(msg_env)

    port = int(os.environ.get("WORKBUDDY_WEB_PORT") or "3081")
    pid = _listener_pid(port)
    if pid:
        ok, msg = _process_has_dshm(pid)
        print(("进程 OK: " if ok else "进程失败: ") + msg)
        if not ok:
            errors.append(msg)
    else:
        print(f"宿主 :{port} 未监听——跳过进程环境检查（打包/未启动时可忽略）")

    if errors:
        print("=== 公司插件市场验收失败（禁止当「官方市场正常」放过）===", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        print(
            "修复: unset DSHM_REGISTRY_URL; scripts/host.sh restart-web\n"
            "破窗（仅调试）: WORKBUDDY_ALLOW_OFFICIAL_MARKET=1\n"
            "约束: .cursor/rules/workbuddy-company-market.mdc （LOCKED）",
            file=sys.stderr,
        )
        return 1
    print("=== 公司插件市场验收 OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
