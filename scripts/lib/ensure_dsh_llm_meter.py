#!/usr/bin/env python3
"""WorkBuddy 预装 @zhongruan/dsh-llm-meter：cordis 启用计量 + profile 依赖/bundles。

只记 llm/stream，无 UI。未进 node_modules 前不写 dependencies，避免 unpublished 拖垮 pnpm。

环境变量（可选）：
  WORKBUDDY_METER_PKG      默认 @zhongruan/dsh-llm-meter
  WORKBUDDY_METER_VERSION  默认 0.1.1
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

METER_PKG = (
    os.environ.get("WORKBUDDY_METER_PKG", "@zhongruan/dsh-llm-meter").strip()
    or "@zhongruan/dsh-llm-meter"
)
METER_VERSION = os.environ.get("WORKBUDDY_METER_VERSION", "0.1.1").strip() or "0.1.1"
METER_ID = "llm-meter"

METER_CONFIG_BLOCK = f"""# --- {METER_ID} (WorkBuddy 预装用量计量；只记 llm/stream) ---
# 用扁平 - id 覆盖 bundles 已装包的配置；禁止 - insert（会与 bundle 同 id 冲突起不来）
- id: {METER_ID}
  name: '{METER_PKG}'
  config:
    enabled: true
    eventsPath: !!js dshHomePath('llm-meter/events.jsonl')
    maxFileBytes: 52428800
"""

# 只匹配 llm-meter 自己的 insert / 扁平块（禁止误吃其它 - insert，如 dsh-mes-bridge）
_METER_BLOCK_RE = re.compile(
    rf"(?ms)^(?:# --- {re.escape(METER_ID)}[^\n]*\n)*"
    rf"(?:# 用扁平[^\n]*\n)?"
    rf"(?:- insert:\s*\n    - id:\s*{re.escape(METER_ID)}\s*\n(?:    [^\n]+\n)+|"
    rf"- id:\s*{re.escape(METER_ID)}\s*\n(?:  [^\n]+\n)*)"
)


def _meter_config_ok(src: str) -> bool:
    """恰好一块扁平 llm-meter（非 insert），且含正确 name、enabled、eventsPath。"""
    matches = list(_METER_BLOCK_RE.finditer(src))
    if len(matches) != 1:
        return False
    block = matches[0].group(0)
    if re.search(r"(?m)^- insert:\s*$", block):
        return False
    return (
        re.search(rf"(?m)^- id:\s*{re.escape(METER_ID)}\s*$", block) is not None
        and re.search(rf"(?m)^\s+name:\s*['\"]?{re.escape(METER_PKG)}['\"]?\s*$", block) is not None
        and re.search(r"(?m)^\s+enabled:\s*true\s*$", block) is not None
        and "eventsPath:" in block
        and "llm-meter/events.jsonl" in block
        and not re.search(r"(?m)^\s+disabled:\s*true\s*$", block)
    )


def _ensure_cordis_patch(patch: Path) -> str:
    if not patch.is_file():
        return f"跳过 cordis：缺少 {patch}"

    src = patch.read_text(encoding="utf-8")
    block = METER_CONFIG_BLOCK.rstrip() + "\n"

    if _meter_config_ok(src):
        return "llm-meter 配置已就绪（enabled + eventsPath）"

    matches = list(_METER_BLOCK_RE.finditer(src))
    if matches:
        new_src = _METER_BLOCK_RE.sub("", src)
        new_src = re.sub(r"\n{3,}", "\n\n", new_src).rstrip() + "\n\n" + block
        patch.write_text(new_src if new_src.endswith("\n") else new_src + "\n", encoding="utf-8")
        return "已修复 llm-meter 配置（去重并启用）"

    stripped = src.rstrip() + "\n"
    if re.search(r"(?m)^\[\]\s*$", stripped):
        stripped = re.sub(r"(?m)^\[\]\s*$", block.rstrip(), stripped)
    else:
        stripped = stripped.rstrip() + "\n\n" + block

    patch.write_text(stripped if stripped.endswith("\n") else stripped + "\n", encoding="utf-8")
    return "已写入 llm-meter（enabled）"


def _node_modules_pkg_json(profile: Path, pkg_name: str) -> Path:
    parts = pkg_name.split("/")
    return profile.joinpath("node_modules", *parts, "package.json")


def package_installed(profile: Path, pkg_name: str | None = None) -> bool:
    return _node_modules_pkg_json(profile, pkg_name or METER_PKG).is_file()


def _ensure_package_json(pkg_path: Path, *, installed: bool) -> tuple[str, bool]:
    """登记计量包。未装进 node_modules 时不写 dependencies，避免拖垮 pnpm。"""
    if not pkg_path.is_file():
        return f"跳过 package.json：缺少 {pkg_path}", False

    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    deps = pkg.setdefault("dependencies", {})
    dsh = pkg.setdefault("dsh", {})
    profile = dsh.setdefault("profile", {})
    bundles = profile.get("bundles")
    if not isinstance(bundles, list):
        bundles = []
        profile["bundles"] = bundles

    changed = False
    notes: list[str] = []
    want = METER_VERSION

    if not installed:
        if METER_PKG in deps or METER_PKG in bundles:
            notes.append(f"已登记 {METER_PKG}，等待安装到 node_modules")
        else:
            notes.append(f"暂不写入 {METER_PKG} 依赖（未安装；由 dsh plugin add 拉取后再登记）")
        profile["bundles"] = bundles
        return ("；".join(notes) if notes else f"等待安装 {METER_PKG}"), False

    cur = deps.get(METER_PKG)
    if not cur:
        deps[METER_PKG] = want
        changed = True
        notes.append(f"已登记 dependencies {METER_PKG}@{want}")
    elif isinstance(cur, str) and cur.startswith("link:"):
        notes.append(f"保留 link 依赖 {METER_PKG}")
    elif cur != want and cur != f"{METER_PKG}@{want}":
        notes.append(f"保留已有 {METER_PKG}@{cur}")

    if METER_PKG not in bundles:
        bundles.append(METER_PKG)
        changed = True
        notes.append(f"已登记 bundles {METER_PKG}")

    profile["bundles"] = bundles
    if changed:
        pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return ("；".join(notes) if notes else f"已登记 {METER_PKG}@{deps.get(METER_PKG, want)}"), True
    return f"{METER_PKG} 已在 dependencies/bundles", False


def ensure_dsh_llm_meter(profile: Path) -> dict:
    profile = profile.expanduser().resolve()
    notes: list[str] = []
    notes.append(_ensure_cordis_patch(profile / "cordis.patch.yml"))
    installed = package_installed(profile)
    msg, _ = _ensure_package_json(profile / "package.json", installed=installed)
    notes.append(msg)
    return {
        "profile": str(profile),
        "pkg": METER_PKG,
        "version": METER_VERSION,
        "installed": installed,
        "need_install": not installed,
        "notes": notes,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(
            f"用法: ensure_dsh_llm_meter.py <profile-dir>\n"
            f"预装 {METER_PKG}@{METER_VERSION}（配置 + 登记依赖；缺包时由调用方 dsh plugin 安装）\n"
            f"可用环境变量 WORKBUDDY_METER_PKG / WORKBUDDY_METER_VERSION 覆盖。",
            file=sys.stderr,
        )
        return 2
    result = ensure_dsh_llm_meter(Path(sys.argv[1]))
    for line in result["notes"]:
        print(line)
    if result["need_install"]:
        print(f"NEED_INSTALL {METER_PKG}@{METER_VERSION}")
        return 0
    print(f"OK {METER_PKG} 已在 node_modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
