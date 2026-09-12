"""两条写码通道互斥：WorkBuddy code-dev 与 DSH @zhongruan/dsh-cursor-coding。

开一条则关另一条。不写死「永远走哪条」；启停仍走功能插件页 / DSH 插件中心。
DSH 侧只改 profile package.json 的 bundles / disabledBundles（与插件中心同语义），
不自动重启宿主。
"""
from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from typing import Any, Dict, Iterator, List

CODE_DEV_FEATURE = "code-dev"
DSH_CURSOR_PKG = "@zhongruan/dsh-cursor-coding"
WB_BEGIN = "mes_code_dev_begin"
DSH_BEGIN = "zr_cursor_begin"


def _profile_manifests() -> Iterator[str]:
    homes: List[str] = []
    env_home = (os.environ.get("DSH_HOME") or "").strip()
    if env_home:
        homes.append(env_home)
    homes.append(os.path.expanduser("~/.dsh"))
    homes.append(os.path.expanduser("~/.dsh-workbuddy"))
    seen = set()
    for home in homes:
        real = os.path.abspath(os.path.expanduser(home))
        if real in seen:
            continue
        seen.add(real)
        path = os.path.join(real, "profiles", "web", "package.json")
        if os.path.isfile(path):
            yield path


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.loads(f.read() or "{}")
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    raw = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".pkg.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _bundle_state(data: Dict[str, Any]) -> tuple[list[str], list[str]]:
    prof = (data.get("dsh") or {}).get("profile") or {}
    if not isinstance(prof, dict):
        prof = {}
    bundles = [str(x) for x in (prof.get("bundles") or [])]
    disabled = [str(x) for x in (prof.get("disabledBundles") or [])]
    return bundles, disabled


def _pkg_installed(data: Dict[str, Any]) -> bool:
    deps = data.get("dependencies") if isinstance(data.get("dependencies"), dict) else {}
    bundles, disabled = _bundle_state(data)
    return DSH_CURSOR_PKG in deps or DSH_CURSOR_PKG in bundles or DSH_CURSOR_PKG in disabled


def is_dsh_cursor_enabled() -> bool:
    """任一活动 profile 的 bundles 含 Cursor 写码包即视为开。"""
    for path in _profile_manifests():
        try:
            data = _read_json(path)
        except Exception:
            continue
        bundles, _disabled = _bundle_state(data)
        if DSH_CURSOR_PKG in bundles:
            return True
    return False


def set_dsh_cursor_enabled(enabled: bool) -> Dict[str, Any]:
    """把 Cursor 写码包在 bundles ↔ disabledBundles 之间移动；未安装则跳过。"""
    updated: List[str] = []
    skipped: List[str] = []
    for path in _profile_manifests():
        try:
            data = _read_json(path)
        except Exception as e:
            skipped.append(f"{path}: {e}")
            continue
        if not _pkg_installed(data):
            continue
        bundles, disabled = _bundle_state(data)
        before = (list(bundles), list(disabled))
        if enabled:
            if DSH_CURSOR_PKG not in bundles:
                bundles.append(DSH_CURSOR_PKG)
            disabled = [x for x in disabled if x != DSH_CURSOR_PKG]
        else:
            bundles = [x for x in bundles if x != DSH_CURSOR_PKG]
            if DSH_CURSOR_PKG not in disabled:
                disabled.append(DSH_CURSOR_PKG)
        if (bundles, disabled) == before:
            continue
        out = deepcopy(data)
        out.setdefault("dsh", {}).setdefault("profile", {})
        out["dsh"]["profile"]["bundles"] = bundles
        out["dsh"]["profile"]["disabledBundles"] = disabled
        try:
            _atomic_write_json(path, out)
        except Exception as e:
            skipped.append(f"{path}: {e}")
            continue
        updated.append(path)
    return {
        "ok": True,
        "enabled": bool(enabled),
        "package": DSH_CURSOR_PKG,
        "updated": updated,
        "skipped": skipped,
    }


def coding_begin(*, workbuddy_on: bool, dsh_on: bool) -> str:
    """当前应调用的写码 begin 工具名；都关则为空。WorkBuddy 开时优先生效。"""
    if workbuddy_on:
        return WB_BEGIN
    if dsh_on:
        return DSH_BEGIN
    return ""


def reconcile() -> Dict[str, Any]:
    """DSH Cursor 写码已在 profile 启用时，自动停用 WorkBuddy code-dev。"""
    from . import plugins_store

    dsh_on = is_dsh_cursor_enabled()
    wb_on = plugins_store.is_enabled(CODE_DEV_FEATURE)
    mutex = ""
    if dsh_on and wb_on:
        plugins_store.disable(CODE_DEV_FEATURE)
        wb_on = False
        mutex = "disabled-code-dev"
    begin = coding_begin(workbuddy_on=wb_on, dsh_on=dsh_on)
    return {
        "ok": True,
        "workbuddy": wb_on,
        "dsh_cursor": dsh_on,
        "begin": begin,
        "mutex": mutex,
    }
