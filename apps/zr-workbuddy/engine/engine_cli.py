"""数据分析引擎 CLI —— 插件经 HTTP /api/cli 调用同一套逻辑；本文件亦可直接命令行调试。

用法：
  python3 engine_cli.py ask "今天正在生产的工单有多少个"
  python3 engine_cli.py status
  python3 engine_cli.py config-test-mes
  python3 engine_cli.py config-test-llm
  python3 engine_cli.py pcb-ask "四层板差分阻抗如何控制"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

_APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app import dns_fix  # noqa: E402

dns_fix.install()

from app.cli_ops import run_async  # noqa: E402


def run_command(cmd: str, *args: str) -> dict:
    """供本地调试；生产路径走 HTTP /api/cli。"""
    try:
        return asyncio.run(run_async(cmd, list(args)))
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "ask"
    out = run_command(cmd, *argv[1:])
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
