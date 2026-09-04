"""第三方 / 自研 feature 安装：校验、目录与 zip 落入、隔离卸载。

真相实现供 HTTP 与 plugin.sh 共用。业务验收看引擎「功能插件」页，不依赖 DSH 是否在跑。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from . import plugins_store
from .config_store import load_config

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
# 禁止把 npm 包拉进 feature（相对 ./ 与裸 Cordis 导出除外由静态规则覆盖）
_NPM_IMPORT_RE = re.compile(
    r"""(?:^|[^\w.])(?:import\s+(?:[\s\S]*?\s+from\s+)?|require\s*\(\s*)['"]([^'"]+)['"]""",
    re.MULTILINE,
)
_EXPORT_NAME_RE = re.compile(r"export\s+const\s+name\b")
_EXPORT_APPLY_RE = re.compile(r"export\s+function\s+apply\s*\(")
_EXPORT_INJECT_RE = re.compile(r"export\s+const\s+inject\b")


def _cfg() -> Dict[str, Any]:
    raw = load_config().get("feature_install") or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "max_zip_bytes": int(raw.get("max_zip_bytes") or 5 * 1024 * 1024),
        "max_files": int(raw.get("max_files") or 200),
        "allow_force": bool(raw.get("allow_force", True)),
    }


def features_dir() -> str:
    return plugins_store.features_dir()


def quarantine_dir() -> str:
    engine_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(engine_root, "data", "feature_quarantine")


def install_tmp_dir() -> str:
    engine_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(engine_root, "data", "feature_install_tmp")


def _is_relative_ok(name: str) -> bool:
    """允许相对路径引用同包文件；拒绝 node 包名与绝对路径。"""
    s = (name or "").strip()
    if not s or s.startswith("/") or s.startswith("node:") or s.startswith("data:"):
        return False
    if s.startswith("./") or s.startswith("../"):
        return True
    # bare specifier = npm / 内置模块
    return False


def scan_index_js(source: str) -> List[str]:
    errors: List[str] = []
    if not _EXPORT_NAME_RE.search(source):
        errors.append("index.js 缺少 export const name")
    if not _EXPORT_APPLY_RE.search(source):
        errors.append("index.js 缺少 export function apply(ctx)")
    if not _EXPORT_INJECT_RE.search(source):
        errors.append("index.js 缺少 export const inject")
    for m in _NPM_IMPORT_RE.finditer(source):
        spec = m.group(1)
        if not _is_relative_ok(spec):
            errors.append(f"禁止 import/require 外部包：{spec}")
    return errors


def _count_files(root: str) -> int:
    n = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        # 跳过隐藏
        base = os.path.basename(dirpath)
        if base.startswith(".") and dirpath != root:
            continue
        n += len(filenames)
    return n


def validate_feature_dir(
    root: str,
    *,
    expect_id: Optional[str] = None,
    max_files: Optional[int] = None,
) -> Dict[str, Any]:
    """校验已展开的 feature 目录。返回 {ok, id, errors, warnings, manifest}。"""
    errors: List[str] = []
    warnings: List[str] = []
    cfg = _cfg()
    limit = max_files if max_files is not None else cfg["max_files"]

    if not root or not os.path.isdir(root):
        return {"ok": False, "id": "", "errors": ["目录不存在"], "warnings": [], "manifest": {}}

    dir_name = os.path.basename(os.path.abspath(root).rstrip(os.sep))
    index_path = os.path.join(root, "index.js")
    man_path = os.path.join(root, "manifest.json")
    readme_path = os.path.join(root, "README.md")

    if not os.path.isfile(index_path):
        errors.append("缺少 index.js")
    if not os.path.isfile(man_path):
        errors.append("缺少 manifest.json")
    if not os.path.isfile(readme_path):
        warnings.append("建议提供 README.md（中文说明）")

    manifest: Dict[str, Any] = {}
    if os.path.isfile(man_path):
        try:
            with open(man_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                errors.append("manifest.json 必须是对象")
            else:
                manifest = data
        except Exception as e:  # noqa: BLE001
            errors.append(f"manifest.json 无法解析：{e}")

    fid = str(manifest.get("id") or "").strip() or dir_name
    if expect_id:
        fid = expect_id
    # 安装过程中的 .partial-* 目录：只按 expect_id / manifest 校验内容，不要求目录名==id
    check_dirname = expect_id is None
    if check_dirname and not _ID_RE.match(dir_name):
        errors.append(f"目录名非法（须小写字母开头、仅 [a-z0-9_-]）：{dir_name}")
    if fid and not _ID_RE.match(fid):
        errors.append(f"manifest.id 非法：{fid}")
    if check_dirname and fid and dir_name != fid:
        errors.append(f"目录名「{dir_name}」与 manifest.id「{fid}」不一致")
    if expect_id and str(manifest.get("id") or "").strip() not in ("", expect_id):
        errors.append(f"期望 id={expect_id}，实际 {manifest.get('id')}")
    elif expect_id and fid != expect_id:
        errors.append(f"期望 id={expect_id}，实际 {fid}")

    for key in ("name", "purpose"):
        if key not in manifest or not str(manifest.get(key) or "").strip():
            errors.append(f"manifest.json 缺少字段：{key}")

    if os.path.isfile(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                src = f.read()
            if len(src) > 1_500_000:
                errors.append("index.js 过大")
            else:
                errors.extend(scan_index_js(src))
        except Exception as e:  # noqa: BLE001
            errors.append(f"无法读取 index.js：{e}")

    try:
        nfiles = _count_files(root)
        if nfiles > limit:
            errors.append(f"文件数超过上限（{nfiles} > {limit}）")
    except Exception as e:  # noqa: BLE001
        warnings.append(f"统计文件数失败：{e}")

    req = manifest.get("requires_engine_commands")
    if isinstance(req, list) and req:
        known = _engine_commands()
        missing = [str(c) for c in req if str(c) not in known]
        if missing:
            warnings.append(
                "needs_engine_merge：本机尚未注册引擎命令 "
                + ", ".join(missing)
                + "（插件可 enable，但相关算数可能不可用）"
            )

    ok = not errors
    return {
        "ok": ok,
        "id": fid if ok or fid else dir_name,
        "errors": errors,
        "warnings": warnings,
        "manifest": manifest,
    }


def _engine_commands() -> set:
    """收集 cli_ops 已注册命令名（读源文件，避免 import 重依赖）。"""
    try:
        path = os.path.join(os.path.dirname(__file__), "cli_ops.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        found = set(re.findall(r'if\s+cmd\s*==\s*["\']([^"\']+)["\']', src))
        return found or {"status", "ask"}
    except Exception:  # noqa: BLE001
        return {"status", "ask"}


def resolve_zip_root(extracted: str) -> Tuple[Optional[str], List[str]]:
    """zip 解压后定位 feature 根：根目录有 index.js，或唯一子目录有 index.js。"""
    errors: List[str] = []
    if os.path.isfile(os.path.join(extracted, "index.js")):
        return extracted, errors
    kids = [
        n
        for n in os.listdir(extracted)
        if not n.startswith(".") and os.path.isdir(os.path.join(extracted, n))
    ]
    if len(kids) == 1:
        cand = os.path.join(extracted, kids[0])
        if os.path.isfile(os.path.join(cand, "index.js")):
            return cand, errors
    # 多子目录时找唯一含 index.js 的
    hits = []
    for n in kids:
        cand = os.path.join(extracted, n)
        if os.path.isfile(os.path.join(cand, "index.js")):
            hits.append(cand)
    if len(hits) == 1:
        return hits[0], errors
    errors.append("zip 内未找到唯一的 feature 根目录（需含 index.js）")
    return None, errors


def safe_extract_zip(zip_path: str, dest: str, *, max_bytes: int, max_files: int) -> List[str]:
    errors: List[str] = []
    try:
        size = os.path.getsize(zip_path)
    except OSError as e:
        return [f"无法读取 zip：{e}"]
    if size > max_bytes:
        return [f"zip 超过大小上限（{size} > {max_bytes} 字节）"]

    dest_abs = os.path.abspath(dest)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            infos = zf.infolist()
            if len(infos) > max_files:
                return [f"zip 内条目数超过上限（{len(infos)} > {max_files}）"]
            total_uncomp = 0
            for info in infos:
                total_uncomp += int(info.file_size or 0)
                if total_uncomp > max_bytes * 8:
                    return ["zip 解压后体积异常（可能为 zip bomb）"]
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    return [f"拒绝不安全的 zip 路径：{info.filename}"]
                target = os.path.abspath(os.path.join(dest_abs, name))
                if not (target == dest_abs or target.startswith(dest_abs + os.sep)):
                    return [f"拒绝 zip-slip 路径：{info.filename}"]
            zf.extractall(dest_abs)
    except zipfile.BadZipFile:
        return ["不是有效的 zip 文件"]
    except Exception as e:  # noqa: BLE001
        return [f"解压失败：{e}"]
    return errors


def preflight_path(path: str) -> Dict[str, Any]:
    """对目录或 zip 做只读校验。"""
    path = os.path.abspath(os.path.expanduser(path or ""))
    if not path or not os.path.exists(path):
        return {"ok": False, "id": "", "errors": ["路径不存在"], "warnings": [], "manifest": {}}

    if os.path.isdir(path):
        return validate_feature_dir(path)

    if not zipfile.is_zipfile(path):
        return {
            "ok": False,
            "id": "",
            "errors": ["既不是目录也不是 zip"],
            "warnings": [],
            "manifest": {},
        }

    cfg = _cfg()
    tmp_root = tempfile.mkdtemp(prefix="feat-preflight-", dir=_ensure_tmp())
    try:
        errs = safe_extract_zip(
            path, tmp_root, max_bytes=cfg["max_zip_bytes"], max_files=cfg["max_files"]
        )
        if errs:
            return {"ok": False, "id": "", "errors": errs, "warnings": [], "manifest": {}}
        root, rerr = resolve_zip_root(tmp_root)
        if not root:
            return {"ok": False, "id": "", "errors": rerr, "warnings": [], "manifest": {}}
        return validate_feature_dir(root)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def _ensure_tmp() -> str:
    d = install_tmp_dir()
    os.makedirs(d, exist_ok=True)
    return d


def _copy_tree(src: str, dst: str) -> None:
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def install_from_dir(
    src_dir: str,
    *,
    force: bool = False,
    enable: bool = True,
) -> Dict[str, Any]:
    cfg = _cfg()
    if force and not cfg["allow_force"]:
        return {"ok": False, "detail": "配置不允许 force 覆盖（feature_install.allow_force=false）"}

    src_dir = os.path.abspath(src_dir)
    report = validate_feature_dir(src_dir)
    if not report["ok"]:
        return {
            "ok": False,
            "detail": "；".join(report["errors"]) or "校验失败",
            "errors": report["errors"],
            "warnings": report["warnings"],
            "id": report.get("id") or "",
        }

    fid = report["id"]
    dest = os.path.join(features_dir(), fid)
    if os.path.exists(dest) and not force:
        return {
            "ok": False,
            "detail": f"已存在 features/{fid}，如需覆盖请 force=true",
            "id": fid,
            "errors": [f"已存在 features/{fid}"],
            "warnings": report["warnings"],
        }

    os.makedirs(features_dir(), exist_ok=True)
    partial = os.path.join(
        features_dir(), f".partial-{fid}-{int(time.time() * 1000)}"
    )
    try:
        _copy_tree(src_dir, partial)
        # 再次校验 partial（防拷贝中途损坏）
        again = validate_feature_dir(partial, expect_id=fid)
        if not again["ok"]:
            shutil.rmtree(partial, ignore_errors=True)
            return {
                "ok": False,
                "detail": "；".join(again["errors"]),
                "errors": again["errors"],
                "warnings": again["warnings"],
                "id": fid,
            }
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.rename(partial, dest)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(partial, ignore_errors=True)
        return {"ok": False, "detail": f"落入失败：{e}", "id": fid}

    out: Dict[str, Any] = {
        "ok": True,
        "id": fid,
        "path": f"features/{fid}",
        "version": (report.get("manifest") or {}).get("version") or "",
        "warnings": report.get("warnings") or [],
        "detail": f"已安装 {fid}",
    }
    if enable:
        en = plugins_store.enable(fid)
        out["enabled"] = bool(en.get("ok"))
        if not en.get("ok"):
            out["warnings"] = list(out["warnings"]) + [en.get("detail") or "enable 失败"]
        else:
            out["detail"] = f"已安装并启用 {fid}"
    return out


def install_from_zip(
    zip_path: str,
    *,
    force: bool = False,
    enable: bool = True,
) -> Dict[str, Any]:
    cfg = _cfg()
    zip_path = os.path.abspath(os.path.expanduser(zip_path))
    if not os.path.isfile(zip_path):
        return {"ok": False, "detail": "zip 文件不存在", "errors": ["zip 文件不存在"]}

    tmp_root = tempfile.mkdtemp(prefix="feat-install-", dir=_ensure_tmp())
    try:
        errs = safe_extract_zip(
            zip_path, tmp_root, max_bytes=cfg["max_zip_bytes"], max_files=cfg["max_files"]
        )
        if errs:
            return {"ok": False, "detail": "；".join(errs), "errors": errs}
        root, rerr = resolve_zip_root(tmp_root)
        if not root:
            return {"ok": False, "detail": "；".join(rerr), "errors": rerr}
        # 若解压根是临时根且子目录名为 id，validate 用子目录名
        return install_from_dir(root, force=force, enable=enable)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def install_source(path: str, *, force: bool = False, enable: bool = True) -> Dict[str, Any]:
    path = os.path.abspath(os.path.expanduser(path or ""))
    if os.path.isdir(path):
        return install_from_dir(path, force=force, enable=enable)
    if os.path.isfile(path) and zipfile.is_zipfile(path):
        return install_from_zip(path, force=force, enable=enable)
    return {"ok": False, "detail": "路径须为 feature 目录或 zip", "errors": ["路径无效"]}


def uninstall_feature(feature_id: str, *, purge: bool = False) -> Dict[str, Any]:
    fid = (feature_id or "").strip()
    if not fid or not _ID_RE.match(fid):
        return {"ok": False, "detail": "非法 feature id"}

    dis = plugins_store.disable(fid)
    if not purge:
        return {
            "ok": True,
            "id": fid,
            "purged": False,
            "detail": dis.get("detail") or f"已停用 {fid}",
            **{k: dis[k] for k in ("available", "enabled") if k in dis},
        }

    src = os.path.join(features_dir(), fid)
    if not os.path.isdir(src):
        return {
            "ok": True,
            "id": fid,
            "purged": False,
            "detail": f"已停用；目录 features/{fid} 不存在，无需隔离",
            **{k: dis[k] for k in ("available", "enabled") if k in dis},
        }

    qroot = quarantine_dir()
    os.makedirs(qroot, exist_ok=True)
    dest = os.path.join(qroot, f"{fid}-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        shutil.move(src, dest)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"移入隔离区失败：{e}", "id": fid}

    snap = plugins_store.snapshot()
    return {
        "ok": True,
        "id": fid,
        "purged": True,
        "quarantine": dest,
        "detail": f"已停用并隔离到 {dest}",
        "available": snap.get("available"),
        "enabled": snap.get("enabled"),
    }


def check_features(ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """批量校验 features/ 下插件（或指定 id）。"""
    root = features_dir()
    results = []
    names: List[str] = []
    if ids:
        names = [i.strip() for i in ids if i and i.strip()]
    elif os.path.isdir(root):
        names = sorted(
            n
            for n in os.listdir(root)
            if not n.startswith(".")
            and os.path.isfile(os.path.join(root, n, "index.js"))
        )
    all_ok = True
    for name in names:
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            results.append(
                {"id": name, "ok": False, "errors": [f"不存在 features/{name}"], "warnings": []}
            )
            all_ok = False
            continue
        rep = validate_feature_dir(path)
        results.append(
            {
                "id": rep.get("id") or name,
                "ok": rep["ok"],
                "errors": rep["errors"],
                "warnings": rep["warnings"],
            }
        )
        if not rep["ok"]:
            all_ok = False
    return {"ok": all_ok, "results": results}


def _main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            json.dumps(
                {
                    "ok": False,
                    "detail": "用法: check|preflight|install|uninstall …",
                },
                ensure_ascii=False,
            )
        )
        return 2
    op = argv[1]
    if op == "check":
        ids = argv[2:] if len(argv) > 2 else None
        print(json.dumps(check_features(ids), ensure_ascii=False, indent=2))
        return 0 if check_features(ids).get("ok") else 1
    if op == "preflight":
        path = argv[2] if len(argv) > 2 else ""
        print(json.dumps(preflight_path(path), ensure_ascii=False, indent=2))
        return 0
    if op == "install":
        path = argv[2] if len(argv) > 2 else ""
        force = "--force" in argv
        print(json.dumps(install_source(path, force=force), ensure_ascii=False, indent=2))
        return 0
    if op == "uninstall":
        fid = argv[2] if len(argv) > 2 else ""
        purge = "--purge" in argv
        print(json.dumps(uninstall_feature(fid, purge=purge), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({"ok": False, "detail": f"未知操作: {op}"}, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
