#!/usr/bin/env python3
"""WorkBuddy 预装 @zhongruan/dsh-knowledge：allowBuilds + cordis 默认关回写 + profile 依赖/bundles。

独立插件仓交付中软包后，本脚本只负责接线预装（整包替换上游 lemoncat7）。
当前宿主若 < 0.1.2-rc.1，回写会因缺 session.snapshotEvents 失败，故默认 extractionEnabled: false。

环境变量（可选）：
  WORKBUDDY_KB_PKG      默认 @zhongruan/dsh-knowledge
  WORKBUDDY_KB_VERSION  默认 1.0.0（与中软仓已发版本对齐；可用环境变量覆盖）
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

KB_PKG = os.environ.get("WORKBUDDY_KB_PKG", "@zhongruan/dsh-knowledge").strip() or "@zhongruan/dsh-knowledge"
KB_VERSION = os.environ.get("WORKBUDDY_KB_VERSION", "1.0.0").strip() or "1.0.0"
KB_ID = "knowledge"

# 禁止与中软包长期并存（会抢 Cordis id: knowledge / 侧栏）
LEGACY_KB_PKGS = (
    "@lemoncat7/dsh-knowledge",
    "dsh-knowledge-base",
)

ALLOW_BUILDS = {
    "esbuild": True,
    "onnxruntime-node": True,
    "protobufjs": True,
    "sharp": True,
    "tesseract.js": False,
}

KNOWLEDGE_CONFIG_BLOCK = f"""# --- {KB_ID} (WorkBuddy 预装知识库；默认关回写) ---
- id: {KB_ID}
  name: '{KB_PKG}'
  config:
    backend: local
    databasePath: !!js dshHomePath('knowledge/knowledge.sqlite')
    connectionPath: !!js dshHomePath('knowledge/connection.json')
    exposeApi: false
    exposeWeb: true
    extractionEnabled: false
"""

_KNOWLEDGE_BLOCK_RE = re.compile(
    rf"(?ms)^(?:# --- {re.escape(KB_ID)}[^\n]*\n)*- id:\s*{KB_ID}\s*\n"
    rf"(?:  name:\s*[^\n]+\n)?  config:\s*\n(?:    [^\n]+\n)*"
)


def _knowledge_config_ok(src: str) -> bool:
    """恰好一块 knowledge，且含 name / databasePath / 关回写。"""
    matches = list(_KNOWLEDGE_BLOCK_RE.finditer(src))
    if len(matches) != 1:
        return False
    block = matches[0].group(0)
    return (
        re.search(rf"(?m)^\s+name:\s*['\"]?{re.escape(KB_PKG)}['\"]?\s*$", block) is not None
        and "databasePath:" in block
        and "connectionPath:" in block
        and re.search(r"(?m)^\s+extractionEnabled:\s*false\s*$", block) is not None
    )


def _ensure_allow_builds(workspace: Path) -> str:
    if not workspace.is_file():
        text = (
            "packages:\n  - .\n\n"
            "nodeLinker: hoisted\n"
            "autoInstallPeers: false\n"
            "allowBuilds:\n"
        )
        for k, v in ALLOW_BUILDS.items():
            text += f"  {k}: {'true' if v else 'false'}\n"
        workspace.write_text(text, encoding="utf-8")
        return "已创建 pnpm-workspace.yaml（含 allowBuilds）"

    src = workspace.read_text(encoding="utf-8")
    if re.search(r"(?m)^allowBuilds:\s*$", src):
        missing = []
        for key, val in ALLOW_BUILDS.items():
            if re.search(rf"(?m)^\s+{re.escape(key)}\s*:", src):
                continue
            missing.append((key, val))
        if not missing:
            return "allowBuilds 已齐全"
        lines = src.splitlines(keepends=True)
        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if not inserted and re.match(r"^allowBuilds:\s*$", line):
                for key, val in missing:
                    out.append(f"  {key}: {'true' if val else 'false'}\n")
                inserted = True
        workspace.write_text("".join(out), encoding="utf-8")
        return f"已补 allowBuilds: {', '.join(k for k, _ in missing)}"

    block = "allowBuilds:\n" + "".join(
        f"  {k}: {'true' if v else 'false'}\n" for k, v in ALLOW_BUILDS.items()
    )
    workspace.write_text(src.rstrip() + "\n\n" + block, encoding="utf-8")
    return "已追加 allowBuilds 块"


def _ensure_cordis_patch(patch: Path) -> str:
    if not patch.is_file():
        return f"跳过 cordis：缺少 {patch}"

    src = patch.read_text(encoding="utf-8")
    block = KNOWLEDGE_CONFIG_BLOCK.rstrip() + "\n"

    if _knowledge_config_ok(src):
        return "knowledge 配置已就绪（含 name/databasePath，关回写）"

    matches = list(_KNOWLEDGE_BLOCK_RE.finditer(src))
    if matches:
        new_src = _KNOWLEDGE_BLOCK_RE.sub("", src)
        new_src = re.sub(r"\n{3,}", "\n\n", new_src).rstrip() + "\n\n" + block
        patch.write_text(new_src if new_src.endswith("\n") else new_src + "\n", encoding="utf-8")
        return "已修复 knowledge 配置（去重并补齐 name/databasePath，关回写）"

    stripped = src.rstrip() + "\n"
    if re.search(r"(?m)^\[\]\s*$", stripped):
        stripped = re.sub(r"(?m)^\[\]\s*$", block.rstrip(), stripped)
    else:
        stripped = stripped.rstrip() + "\n\n" + block

    patch.write_text(stripped if stripped.endswith("\n") else stripped + "\n", encoding="utf-8")
    return "已写入 knowledge.extractionEnabled: false"


def _node_modules_pkg_json(profile: Path, pkg_name: str) -> Path:
    """@scope/name → node_modules/@scope/name/package.json"""
    parts = pkg_name.split("/")
    return profile.joinpath("node_modules", *parts, "package.json")


def package_installed(profile: Path, pkg_name: str | None = None) -> bool:
    return _node_modules_pkg_json(profile, pkg_name or KB_PKG).is_file()


def _ensure_package_json(pkg_path: Path, *, installed: bool) -> tuple[str, bool]:
    """登记中软包 / 卸遗留包。

    中软包尚未装进 node_modules 时：
    - **不**写入 dependencies（避免 unpublished 拖垮 `pnpm install` / bridge 接线）
    - **不**卸 lemoncat7 等遗留包（等中软包装上再替换，避免现场空窗）
    """
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
    want = KB_VERSION

    if not installed:
        # 已有登记则保留（可能正由 dsh plugin add / pnpm 拉取）；不要主动写入新依赖
        if KB_PKG in deps or KB_PKG in bundles:
            notes.append(f"已登记 {KB_PKG}，等待安装到 node_modules")
        else:
            notes.append(f"暂不写入 {KB_PKG} 依赖（未安装；由 dsh plugin add 拉取后再登记）")
        # 若上次失败残留不可解析依赖，清掉以免拖垮 bridge 的 pnpm install
        if KB_PKG in deps and not str(deps.get(KB_PKG, "")).startswith("link:"):
            # 保留：调用方可能刚写入正要 install；仅当明确要求 purge stale 时再删
            pass
        profile["bundles"] = bundles
        return ("；".join(notes) if notes else f"等待安装 {KB_PKG}"), False

    for legacy in LEGACY_KB_PKGS:
        if legacy == KB_PKG:
            continue
        if legacy in deps:
            del deps[legacy]
            changed = True
            notes.append(f"已从 dependencies 移除 {legacy}")
        if legacy in bundles:
            bundles[:] = [b for b in bundles if b != legacy]
            changed = True
            notes.append(f"已从 bundles 移除 {legacy}")

    cur = deps.get(KB_PKG)
    if not cur:
        deps[KB_PKG] = want
        changed = True
        notes.append(f"已登记 dependencies {KB_PKG}@{want}")
    elif isinstance(cur, str) and cur.startswith("link:"):
        notes.append(f"保留 link 依赖 {KB_PKG}")
    elif cur != want and cur != f"{KB_PKG}@{want}":
        notes.append(f"保留已有 {KB_PKG}@{cur}")

    if KB_PKG not in bundles:
        bundles.append(KB_PKG)
        changed = True
        notes.append(f"已登记 bundles {KB_PKG}")

    profile["bundles"] = bundles
    if changed:
        pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return ("；".join(notes) if notes else f"已登记 {KB_PKG}@{deps.get(KB_PKG, want)}"), True
    return f"{KB_PKG} 已在 dependencies/bundles", False


def ensure_dsh_knowledge(profile: Path) -> dict:
    profile = profile.expanduser().resolve()
    notes: list[str] = []
    notes.append(_ensure_allow_builds(profile / "pnpm-workspace.yaml"))
    notes.append(_ensure_cordis_patch(profile / "cordis.patch.yml"))
    installed = package_installed(profile)
    msg, _ = _ensure_package_json(profile / "package.json", installed=installed)
    notes.append(msg)
    return {
        "profile": str(profile),
        "pkg": KB_PKG,
        "version": KB_VERSION,
        "installed": installed,
        "need_install": not installed,
        "notes": notes,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(
            f"用法: ensure_dsh_knowledge.py <profile-dir>\n"
            f"预装 {KB_PKG}@{KB_VERSION}（配置 + 登记依赖；缺包时由调用方 pnpm/dsh plugin 安装）\n"
            f"可用环境变量 WORKBUDDY_KB_PKG / WORKBUDDY_KB_VERSION 覆盖。",
            file=sys.stderr,
        )
        return 2
    result = ensure_dsh_knowledge(Path(sys.argv[1]))
    for line in result["notes"]:
        print(line)
    if result["need_install"]:
        print(f"NEED_INSTALL {KB_PKG}@{KB_VERSION}")
        return 0
    print(f"OK {KB_PKG} 已在 node_modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
