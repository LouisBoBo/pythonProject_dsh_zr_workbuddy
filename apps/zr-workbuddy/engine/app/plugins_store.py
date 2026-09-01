"""功能插件（features）启停状态 —— 热插拔单一真相源。

写路径：flock + 临时文件 os.replace，供引擎 API / bridge / plugin.sh 共用，避免并发丢改。

**自动发现（硬性约定）**：
- 「功能插件」管理页 / `/api/plugins` 的 available **只扫描** `features/*/index.js`
- **禁止**在前端或 API 里写死插件 id 白名单；新增 feature 目录即自动出现，可启停
- mes-bridge / mes-runtime 等系统性组件不在 features/ 下，故不会进入管理列表
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
from typing import Any, Callable, Dict, List, TypeVar

_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATE_PATH = os.path.join(_ENGINE_ROOT, "data", "plugins.json")
_LOCK_PATH = _STATE_PATH + ".lock"
_FEATURES_DIR = os.path.join(os.path.dirname(_ENGINE_ROOT), "features")

T = TypeVar("T")


def features_dir() -> str:
    return _FEATURES_DIR


def state_path() -> str:
    return _STATE_PATH


def list_available() -> List[Dict[str, Any]]:
    """扫描 features/：凡含 index.js 的目录即视为可管理的功能插件。

    新增功能只需落地 features/<id>/，无需改管理页或本函数白名单。
    """
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(_FEATURES_DIR):
        return out
    for name in sorted(os.listdir(_FEATURES_DIR)):
        # 跳过隐藏目录与非包目录
        if name.startswith("."):
            continue
        root = os.path.join(_FEATURES_DIR, name)
        index = os.path.join(root, "index.js")
        if not os.path.isdir(root) or not os.path.isfile(index):
            continue
        meta: Dict[str, Any] = {
            "id": name,
            "name": name,
            "purpose": "",
            "kind": "feature",
            "path": f"features/{name}",
        }
        man = os.path.join(root, "manifest.json")
        if os.path.isfile(man):
            try:
                with open(man, encoding="utf-8") as f:
                    data = json.loads(f.read())
                if isinstance(data, dict):
                    meta.update({k: data[k] for k in ("id", "name", "purpose") if k in data})
                    meta["id"] = name
                    meta["kind"] = "feature"
                    meta["path"] = f"features/{name}"
            except Exception:
                pass
        out.append(meta)
    return out


def _default_enabled() -> List[str]:
    return [m["id"] for m in list_available()]


def _with_lock(fn: Callable[[], T]) -> T:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_LOCK_PATH, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _atomic_write(obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    raw = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(_STATE_PATH),
        prefix=".plugins.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _STATE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_unlocked() -> Dict[str, Any]:
    if not os.path.isfile(_STATE_PATH):
        st = {"enabled": _default_enabled()}
        _atomic_write(st)
        return st
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            data = json.loads(f.read())
        if not isinstance(data, dict):
            raise ValueError("invalid")
        enabled = data.get("enabled")
        if not isinstance(enabled, list):
            enabled = _default_enabled()
        return {"enabled": [str(x) for x in enabled]}
    except Exception:
        st = {"enabled": _default_enabled()}
        _atomic_write(st)
        return st


def load_state() -> Dict[str, Any]:
    return _with_lock(_read_unlocked)


def save_state(state: Dict[str, Any]) -> Dict[str, Any]:
    def _do() -> Dict[str, Any]:
        enabled = [str(x) for x in (state.get("enabled") or [])]
        seen = set()
        uniq = []
        for x in enabled:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        out = {"enabled": uniq}
        _atomic_write(out)
        return out

    return _with_lock(_do)


def snapshot() -> Dict[str, Any]:
    available = list_available()
    ids = {m["id"] for m in available}
    st = load_state()
    enabled = [i for i in st["enabled"] if i in ids]
    return {
        "ok": True,
        "available": available,
        "enabled": enabled,
        "state_path": _STATE_PATH,
    }


def is_enabled(feature_id: str) -> bool:
    """feature 是否在 plugins.json 启停真相源中启用。"""
    fid = (feature_id or "").strip()
    if not fid:
        return False
    snap = snapshot()
    return fid in (snap.get("enabled") or [])


def disabled_hint(feature_id: str, *, capability: str = "") -> str:
    """统一的功能停用提示（面板 / CLI / Agent 共用）。"""
    fid = (feature_id or "").strip() or "unknown"
    cap = (capability or "").strip() or "相关能力"
    return (
        f"「{cap}」对应的功能插件（{fid}）当前已停用，因此不可用。\n\n"
        f"重新开启：\n"
        f"`scripts/plugin.sh --app zr-workbuddy enable {fid}`\n\n"
        "约 1 秒内热加载，无需重启 DSH。"
    )


def require_enabled(feature_id: str, *, capability: str = "") -> Dict[str, Any] | None:
    """已启用返回 None；未启用返回标准禁用响应（ok=False，供 CLI/工具）。"""
    if is_enabled(feature_id):
        return None
    fid = (feature_id or "").strip()
    return {
        "ok": False,
        "detail": disabled_hint(fid, capability=capability),
        "source": "disabled",
        "note": f"{fid} 未启用",
    }

def enable(feature_id: str) -> Dict[str, Any]:
    fid = (feature_id or "").strip()
    ids = {m["id"] for m in list_available()}
    if fid not in ids:
        return {"ok": False, "detail": f"未知 feature: {fid}"}

    def _do() -> Dict[str, Any]:
        st = _read_unlocked()
        if fid not in st["enabled"]:
            st["enabled"].append(fid)
            _atomic_write({"enabled": st["enabled"]})
        return {"ok": True, "detail": f"已启用 {fid}"}

    out = _with_lock(_do)
    if not out.get("ok"):
        return out
    return {**out, **snapshot()}


def disable(feature_id: str) -> Dict[str, Any]:
    fid = (feature_id or "").strip()

    def _do() -> Dict[str, Any]:
        st = _read_unlocked()
        if fid in st["enabled"]:
            st["enabled"] = [x for x in st["enabled"] if x != fid]
            _atomic_write({"enabled": st["enabled"]})
        return {"ok": True, "detail": f"已停用 {fid}"}

    out = _with_lock(_do)
    return {**out, **snapshot()}


def _main(argv: List[str]) -> int:
    """供 bridge / plugin.sh 调用：python -m app.plugins_store <enable|disable|load|save> …"""
    if len(argv) < 2:
        print(json.dumps({"ok": False, "detail": "用法: enable|disable|load|save"}, ensure_ascii=False))
        return 2
    op = argv[1]
    if op == "enable":
        print(json.dumps(enable(argv[2] if len(argv) > 2 else ""), ensure_ascii=False))
        return 0
    if op == "disable":
        print(json.dumps(disable(argv[2] if len(argv) > 2 else ""), ensure_ascii=False))
        return 0
    if op == "load":
        print(json.dumps(load_state(), ensure_ascii=False))
        return 0
    if op == "save":
        enabled = json.loads(argv[2]) if len(argv) > 2 else []
        print(json.dumps(save_state({"enabled": enabled}), ensure_ascii=False))
        return 0
    if op == "snapshot":
        print(json.dumps(snapshot(), ensure_ascii=False))
        return 0
    print(json.dumps({"ok": False, "detail": f"未知操作: {op}"}, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
