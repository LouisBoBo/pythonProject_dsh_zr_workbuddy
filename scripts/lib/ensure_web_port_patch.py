#!/usr/bin/env python3
"""在 WorkBuddy profile 的 cordis.patch.yml 固定 webserver 端口（默认 3081）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WEBSERVER_BLOCK = """- id: webserver
  config:
    host: 127.0.0.1
    port: {port}
"""


def ensure_web_port_patch(profile: Path, port: int = 3081) -> str:
    patch = profile / "cordis.patch.yml"
    if not patch.is_file():
        raise SystemExit(f"缺少 {patch}")

    src = patch.read_text(encoding="utf-8")
    block = WEBSERVER_BLOCK.format(port=port).rstrip() + "\n"

    if re.search(r"(?m)^- id: webserver\s*$", src):
        new_src, n = re.subn(
            r"(?ms)^- id: webserver\s*\n  config:\s*\n    host: [^\n]+\n    port: \d+\s*\n",
            block,
            src,
            count=1,
        )
        if n:
            patch.write_text(new_src if new_src.endswith("\n") else new_src + "\n", encoding="utf-8")
            return f"已更新 webserver → :{port}"
        if f"port: {port}" in src:
            return f"webserver 已是 :{port}"
        patch.write_text(src.rstrip() + "\n\n" + block, encoding="utf-8")
        return f"已追加 webserver :{port}（原块格式非常规）"

    # 空数组占位 [] 不能与后续 patch 并存
    stripped = src.rstrip() + "\n"
    if re.search(r"(?m)^\[\]\s*$", stripped):
        stripped = re.sub(r"(?m)^\[\]\s*$", block.rstrip(), stripped)
    else:
        # 插在注释头之后、第一个 - insert / - id 之前
        m = re.search(r"(?m)^- ", stripped)
        if m:
            stripped = stripped[: m.start()] + block + "\n" + stripped[m.start() :]
        else:
            stripped = stripped.rstrip() + "\n\n" + block

    patch.write_text(stripped if stripped.endswith("\n") else stripped + "\n", encoding="utf-8")
    return f"已写入 webserver → :{port}"


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: ensure_web_port_patch.py <profile-dir> [port]", file=sys.stderr)
        return 2
    profile = Path(sys.argv[1]).expanduser()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 3081
    print(ensure_web_port_patch(profile, port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
