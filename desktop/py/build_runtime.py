#!/usr/bin/env python3
"""构建桌面运行时：standalone CPython + venv + apps/zr-workbuddy（对齐 simplified）。

产出 desktop/runtime/
  python/   # venv
  app/      # 业务应用树
  bin/workbuddy-engine
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "desktop" / "runtime"
CACHE = OUT / "_cache"
STANDALONE_ROOT = OUT / "_cpython"
VENV = OUT / "python"
APP = OUT / "app"
BIN = OUT / "bin"

CPYTHON_TAG = "20250317"
CPYTHON_VERSION = "3.12.9"


def _log(msg: str) -> None:
    print(f"[build-runtime] {msg}", flush=True)


def _run(cmd: list[str], **kwargs) -> None:
    _log("+ " + " ".join(cmd))
    subprocess.check_call(cmd, **kwargs)


def _platform_triplet() -> tuple[str, str]:
    sysname = platform.system().lower()
    machine = platform.machine().lower()
    if sysname == "darwin":
        if machine in ("arm64", "aarch64"):
            return "aarch64-apple-darwin", "macOS Apple Silicon"
        return "x86_64-apple-darwin", "macOS Intel/Rosetta"
    if sysname == "windows":
        if machine in ("arm64", "aarch64"):
            return "aarch64-pc-windows-msvc", "Windows ARM64"
        return "x86_64-pc-windows-msvc", "Windows x64"
    if sysname == "linux":
        if machine in ("arm64", "aarch64"):
            return "aarch64-unknown-linux-gnu", "Linux ARM64"
        return "x86_64-unknown-linux-gnu", "Linux x64"
    raise RuntimeError(f"暂不支持打包平台: {sysname}/{machine}")


def ensure_standalone_python() -> Path:
    triplet, label = _platform_triplet()
    _log(f"目标平台: {label} ({triplet})")
    name = f"cpython-{CPYTHON_VERSION}+{CPYTHON_TAG}-{triplet}-install_only.tar.gz"
    url = (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        f"{CPYTHON_TAG}/{name}"
    )
    CACHE.mkdir(parents=True, exist_ok=True)
    tarball = CACHE / name
    if not tarball.is_file():
        _log(f"下载 {url}")
        urllib.request.urlretrieve(url, tarball)
    else:
        _log(f"使用缓存 {tarball}")

    if STANDALONE_ROOT.exists():
        shutil.rmtree(STANDALONE_ROOT)
    STANDALONE_ROOT.mkdir(parents=True, exist_ok=True)
    _log(f"解压 → {STANDALONE_ROOT}")
    with tarfile.open(tarball, "r:gz") as tf:
        tf.extractall(STANDALONE_ROOT)

    py = STANDALONE_ROOT / "python" / "bin" / ("python.exe" if os.name == "nt" else "python3")
    if not py.is_file():
        alt = STANDALONE_ROOT / "bin" / ("python.exe" if os.name == "nt" else "python3")
        if alt.is_file():
            return alt
        raise FileNotFoundError(f"解压后未找到 python: {py}")
    return py


def create_venv(standalone_py: Path) -> Path:
    """把 standalone CPython 整树拷进 runtime/python（解引用符号链接，保证可随包迁移）。

    不用 venv：venv 会把 home 写成构建机绝对路径，打进 .app 后 python 断链。
    """
    src_root = standalone_py.resolve().parent.parent  # .../python
    if not (src_root / "bin").is_dir() and not (src_root / "Scripts").is_dir():
        raise FileNotFoundError(f"standalone 根目录异常: {src_root}")
    if VENV.exists():
        shutil.rmtree(VENV)
    _log(f"复制可迁移 Python → {VENV}（from {src_root}）")
    shutil.copytree(src_root, VENV, symlinks=False)
    if os.name == "nt":
        py = VENV / "Scripts" / "python.exe"
    else:
        py = VENV / "bin" / "python3"
        # 统一提供 bin/python
        py_link = VENV / "bin" / "python"
        if py.is_file() and not py_link.exists():
            py_link.symlink_to("python3")
    if not py.is_file():
        raise FileNotFoundError(f"复制后未找到解释器: {py}")
    # 冒烟：解释器必须是真实文件或相对链，不能再指到仓库外绝对路径
    real = py.resolve()
    if not str(real).startswith(str(VENV.resolve())):
        raise RuntimeError(f"Python 未封闭在 runtime/python 内: {real}")
    return py


def pip_install(venv_py: Path) -> None:
    req = REPO / "apps" / "zr-workbuddy" / "engine" / "requirements.txt"
    _run([str(venv_py), "-m", "pip", "install", "-U", "pip", "wheel"])
    _run([str(venv_py), "-m", "pip", "install", "-r", str(req)])
    _run(
        [
            str(venv_py),
            "-c",
            "import fastapi, uvicorn, yaml, httpx, numpy; print('runtime_import_ok')",
        ]
    )


def materialize_bridge_node_modules(app_root: Path) -> None:
    """打包时忽略了 plugins 下 node_modules；Node 解析 import 需要真实 node_modules。"""
    bridge = app_root / "apps" / "zr-workbuddy" / "plugins" / "mes-bridge"
    tools_src = app_root / "vendor" / "@deepseek-ai" / "dsh-tools"
    runtime_src = app_root / "apps" / "zr-workbuddy" / "plugins" / "mes-runtime"
    if not bridge.is_dir():
        raise FileNotFoundError(bridge)
    nm = bridge / "node_modules"
    tools_dst = nm / "@deepseek-ai" / "dsh-tools"
    runtime_dst = nm / "@dsh-external" / "mes-runtime"
    if tools_src.is_dir():
        if tools_dst.exists():
            shutil.rmtree(tools_dst)
        tools_dst.parent.mkdir(parents=True, exist_ok=True)
        _copytree(tools_src, tools_dst)
        _log("物化 mes-bridge → @deepseek-ai/dsh-tools")
    else:
        _log(f"警告: 缺少 {tools_src}")
    if runtime_src.is_dir():
        runtime_dst.parent.mkdir(parents=True, exist_ok=True)
        if runtime_dst.exists() or runtime_dst.is_symlink():
            runtime_dst.unlink() if runtime_dst.is_symlink() else shutil.rmtree(runtime_dst)
        # 相对链接：node_modules/@dsh-external/mes-runtime → ../../mes-runtime
        os.symlink(os.path.join("..", "..", "..", "mes-runtime"), runtime_dst)
        _log("物化 mes-bridge → @dsh-external/mes-runtime")


_JUNK_NAMES = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "config.yaml",
    "chat_log.jsonl",
    "engine.pid",
    "engine.log",
    "charts",
    ".mplcache",
    "local_dev",
    "sandboxes",
    "feature_quarantine",
    "feature_install_tmp",
    "_test_*",
    "_git_probe",
    "_empty_tpl",
)


def _ignore_copy(directory: str, names: list[str]) -> set[str]:
    """忽略缓存/密钥/运行时数据；不得按目录名丢掉 app/code_* 源码包。"""
    skipped = set(_JUNK_NAMES(directory, names))
    here = Path(directory)
    # engine/data 下除 plugins.json 外都是 Job/沙箱落盘，不进安装包
    if here.name == "data" and here.parent.name == "engine":
        skipped.update(n for n in names if n != "plugins.json")
    return skipped


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore_copy)


def _assert_workbuddy_capabilities(app_root: Path) -> None:
    """打包后必须仍有写码/审码/提交/部署算数与 features，禁止再静默丢模块。"""
    engine_app = app_root / "engine" / "app"
    for pkg in ("code_dev", "code_review", "code_commit", "code_deploy", "hitl"):
        init = engine_app / pkg / "__init__.py"
        if not init.is_file():
            raise FileNotFoundError(f"打包漏了引擎模块 {pkg}（{init}）")
    features = app_root / "features"
    for fid in (
        "code-dev",
        "code-review",
        "code-commit",
        "code-deploy",
        "mes-ask",
        "mes-config",
        "mes-pcb",
    ):
        manifest = features / fid / "manifest.json"
        index = features / fid / "index.js"
        if not manifest.is_file() or not index.is_file():
            raise FileNotFoundError(f"打包漏了 feature {fid}")
    _log("能力校验通过：code_dev/review/commit/deploy + 7 个 features")


def sync_app_sources() -> None:
    if APP.exists():
        shutil.rmtree(APP)
    app_root = APP / "apps" / "zr-workbuddy"
    app_root.mkdir(parents=True)
    for name in ("engine", "plugins", "features"):
        src = REPO / "apps" / "zr-workbuddy" / name
        if not src.is_dir():
            raise FileNotFoundError(src)
        _log(f"复制 apps/zr-workbuddy/{name}")
        _copytree(src, app_root / name)

    # 示例配置 → 安装包内模板（真密钥不进包）
    example = REPO / "apps" / "zr-workbuddy" / "engine" / "config" / "config.example.yaml"
    cfg_dir = app_root / "engine" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    if example.is_file():
        shutil.copy2(example, cfg_dir / "config.example.yaml")
        # 首次可写副本名，运行时若无 config.yaml 由 main 复制
        shutil.copy2(example, cfg_dir / "config.yaml")

    # runtime.yaml 固定回环；端口由桌面壳注入环境覆盖时仍以文件为准，打包用高位口模板
    runtime = cfg_dir / "runtime.yaml"
    runtime.write_text(
        "server:\n  host: 127.0.0.1\n  port: 18000\n"
        "python: python3\n",
        encoding="utf-8",
    )

    py_dst = APP / "desktop" / "py"
    py_dst.mkdir(parents=True)
    shutil.copy2(REPO / "desktop" / "py" / "run_engine.py", py_dst / "run_engine.py")

    # mes-runtime 经 REPO_ROOT/scripts/lib/read_runtime.py 读端口；一体包须自带
    scripts_lib = APP / "scripts" / "lib"
    scripts_lib.mkdir(parents=True)
    shutil.copy2(REPO / "scripts" / "lib" / "read_runtime.py", scripts_lib / "read_runtime.py")

    # mes-bridge → link:../../../../vendor/@deepseek-ai/dsh-tools
    vendor_src = REPO / "vendor" / "@deepseek-ai" / "dsh-tools"
    if vendor_src.is_dir():
        vendor_dst = APP / "vendor" / "@deepseek-ai" / "dsh-tools"
        vendor_dst.parent.mkdir(parents=True, exist_ok=True)
        _log("复制 vendor/@deepseek-ai/dsh-tools")
        _copytree(vendor_src, vendor_dst)
    else:
        _log(f"警告: 缺少 {vendor_src}，Bridge 安装可能失败")

    materialize_bridge_node_modules(APP)
    _assert_workbuddy_capabilities(app_root)

    ver = {
        "product": "ZR WorkBuddy",
        "desktop_version": _read_desktop_version(),
        "git_commit": _git_commit(),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": CPYTHON_VERSION,
    }
    (APP / "version.json").write_text(
        json.dumps(ver, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _log(f"版本清单 → {ver}")


def _read_desktop_version() -> str:
    pkg = REPO / "desktop" / "package.json"
    try:
        return str(json.loads(pkg.read_text(encoding="utf-8")).get("version") or "0.0.0")
    except Exception:
        return "0.0.0"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def write_launchers() -> None:
    BIN.mkdir(parents=True, exist_ok=True)
    engine = BIN / ("workbuddy-engine.cmd" if os.name == "nt" else "workbuddy-engine")
    if os.name == "nt":
        engine.write_text(
            "@echo off\r\n"
            "set ROOT=%~dp0..\r\n"
            "set WORKBUDDY_ENGINE_DIR=%ROOT%\\app\\apps\\zr-workbuddy\\engine\r\n"
            "\"%ROOT%\\python\\Scripts\\python.exe\" \"%ROOT%\\app\\desktop\\py\\run_engine.py\" %*\r\n",
            encoding="utf-8",
        )
    else:
        engine.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'ROOT="$(cd "$(dirname "$0")/.." && pwd)"\n'
            'export WORKBUDDY_ENGINE_DIR="$ROOT/app/apps/zr-workbuddy/engine"\n'
            'exec "$ROOT/python/bin/python3" "$ROOT/app/desktop/py/run_engine.py" "$@"\n',
            encoding="utf-8",
        )
        engine.chmod(engine.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    app_only = len(sys.argv) > 1 and sys.argv[1] in ("--app-only", "app", "sync-app")
    if not app_only:
        standalone = ensure_standalone_python()
        venv_py = create_venv(standalone)
        pip_install(venv_py)
    sync_app_sources()
    write_launchers()

    def _du(path: Path) -> str:
        try:
            return subprocess.check_output(["du", "-sh", str(path)], text=True).split()[0]
        except Exception:
            return "?"

    _log(f"完成 → {OUT}  python={_du(VENV)} app={_du(APP)}")
    _log("下一步: ./scripts/package-desktop.sh")


if __name__ == "__main__":
    main()
