#!/usr/bin/env python3
"""把命令放到新会话里后台跑，避免 Cursor/IDE 结束 shell 时把子进程带走。

用法:
  python3 scripts/lib/daemonize.py --cwd DIR --log FILE --pid FILE -- cmd [args...]
打印子进程 PID 到 stdout。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Detached process launcher")
    ap.add_argument("--cwd", default=os.path.expanduser("~"))
    ap.add_argument("--log", required=True)
    ap.add_argument("--pid", required=True)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("daemonize: missing command", file=sys.stderr)
        return 2

    log_path = Path(args.log).expanduser()
    pid_path = Path(args.pid).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    cwd = str(Path(args.cwd).expanduser())
    # 追加日志；子进程继承后父进程立即关闭 fd
    log_f = open(log_path, "ab", buffering=0)
    try:
        # start_new_session=True → 子进程 setsid，脱离控制终端与父进程组
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            env=os.environ.copy(),
        )
    finally:
        try:
            log_f.close()
        except OSError:
            pass

    pid_path.write_text(f"{proc.pid}\n", encoding="utf-8")
    print(proc.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
