#!/usr/bin/env python3
"""唯一 runtime.yaml 解析实现。框架脚本 / 引擎 / mes-runtime 均应调用本文件。

用法:
  python3 scripts/lib/read_runtime.py <runtime.yaml路径|engine目录>
  → stdout 一行 JSON: {"host","port","python"}

环境变量覆盖（与历史约定一致）:
  APP_ENGINE_HOST / APP_ENGINE_PORT / APP_ENGINE_PYTHON
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict


DEFAULTS: Dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8000,
    "python": "python3",
}


def resolve_yaml_path(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.join(arg, "config", "runtime.yaml")
    return arg


def parse_runtime_yaml(text: str) -> Dict[str, Any]:
    out = dict(DEFAULTS)
    m = re.search(r"^\s*host:\s*(\S+)", text, re.M)
    if m:
        out["host"] = m.group(1).strip("'\"")
    m = re.search(r"^\s*port:\s*(\d+)", text, re.M)
    if m:
        out["port"] = int(m.group(1))
    m = re.search(r"^\s*python:\s*(\S+)", text, re.M)
    if m:
        out["python"] = m.group(1).strip("'\"")
    return out


def read_runtime(path_or_engine: str) -> Dict[str, Any]:
    path = resolve_yaml_path(path_or_engine)
    out = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            out = parse_runtime_yaml(f.read())
    except Exception:
        pass
    host = os.environ.get("APP_ENGINE_HOST") or out["host"]
    port = os.environ.get("APP_ENGINE_PORT") or out["port"]
    python = os.environ.get("APP_ENGINE_PYTHON") or out["python"]
    try:
        port = int(port)
    except Exception:
        port = DEFAULTS["port"]
    return {"host": str(host), "port": port, "python": str(python)}


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: read_runtime.py <runtime.yaml|engine目录>", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(read_runtime(sys.argv[1]), ensure_ascii=False))


if __name__ == "__main__":
    main()
