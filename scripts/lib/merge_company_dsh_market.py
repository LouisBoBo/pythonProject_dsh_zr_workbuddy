#!/usr/bin/env python3
"""合并公司 DSH 插件目录与官方 awesome-dsh-plugin 目录。

约束：
- 公司插件永远可展示：公司站失败时用缓存，再失败用仓库种子；从不因官方失败而清空。
- 官方目录每天最多成功同步一次；失败后 6 小时内不重试。
- 公司插件在合并结果里排在最前（含 dshmarket 默认按 downloads 排序时的置顶）。
- 只绑 127.0.0.1 提供合并后的 plugins.json，供 DSHM_REGISTRY_URL 使用。

用法：
  python3 merge_company_dsh_market.py ensure --root REPO [--cache-dir DIR]
  python3 merge_company_dsh_market.py write --out plugins.json
  python3 merge_company_dsh_market.py refresh-official
  python3 merge_company_dsh_market.py serve --port 18731
"""
from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows 桌面包极少走到这里
    fcntl = None  # type: ignore[assignment]

DEFAULT_COMPANY_URL = "http://175.178.238.31/dsh-plugins/plugins.json"
DEFAULT_OFFICIAL_URL = "https://awesome-dsh-plugin.com/plugins.json"
DEFAULT_NPM_REGISTRY = "https://mirrors.cloud.tencent.com/npm"
CATALOG_PACKAGE = "dsh-plugin-catalog"
DEFAULT_PORT = 18731
COMPANY_TIMEOUT_S = 4.0
OFFICIAL_TIMEOUT_S = 15.0
OFFICIAL_TTL_S = 24 * 3600
OFFICIAL_FAIL_BACKOFF_S = 6 * 3600
USER_AGENT = "WorkBuddy-market-merge/1.0"
SERVICE_NAME = "workbuddy-market-merge"
ZHONGRUAN_CATEGORY = "zhongruan"
HTTP_MAX_BYTES = 20 * 1024 * 1024


def _today() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


def plugin_identity(plugin: dict[str, Any]) -> str:
    npm = str(plugin.get("npm") or "").strip()
    name = str(plugin.get("name") or "").strip()
    return (npm or name).lower()


def plugin_categories_list(plugin: dict[str, Any]) -> list[str]:
    raw = plugin.get("category")
    values = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or value == "" or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def catalog_usable(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    plugins = data.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        return False
    return any(isinstance(p, dict) and plugin_identity(p) for p in plugins)


def _numeric_max(plugins: list[dict[str, Any]], field: str) -> int:
    best = 0
    for plugin in plugins:
        value = plugin.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value > best:
            best = int(value)
    return best


def pin_company_plugins(
    company_plugins: list[dict[str, Any]],
    official_plugins: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """复制公司条目并加上排序钉，不改缓存里的原始公司目录。"""
    max_dl = _numeric_max(official_plugins, "downloads")
    max_st = _numeric_max(official_plugins, "stars")
    n = len(company_plugins)
    pinned: list[dict[str, Any]] = []
    for i, plugin in enumerate(company_plugins):
        row = dict(plugin)
        bump = n - i
        row["downloads"] = max_dl + bump
        row["stars"] = max_st + bump
        cats = plugin_categories_list(row)
        if ZHONGRUAN_CATEGORY not in cats:
            row["category"] = [ZHONGRUAN_CATEGORY, *cats] if cats else [ZHONGRUAN_CATEGORY, "tools"]
        pinned.append(row)
    return pinned


def merge_catalogs(company: dict[str, Any], official: dict[str, Any] | None) -> dict[str, Any]:
    company_plugins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for plugin in company.get("plugins") or []:
        if not isinstance(plugin, dict):
            continue
        key = plugin_identity(plugin)
        if not key or key in seen:
            continue
        seen.add(key)
        company_plugins.append(plugin)

    official_plugins: list[dict[str, Any]] = []
    official_cats: dict[str, Any] = {}
    if isinstance(official, dict):
        cats = official.get("categories")
        if isinstance(cats, dict):
            official_cats = dict(cats)
        for plugin in official.get("plugins") or []:
            if not isinstance(plugin, dict):
                continue
            key = plugin_identity(plugin)
            if not key or key in seen:
                continue
            seen.add(key)
            official_plugins.append(plugin)

    categories: dict[str, Any] = {
        ZHONGRUAN_CATEGORY: {"zh": "中软", "en": "Zhongruan"},
    }
    for key, value in official_cats.items():
        if key != ZHONGRUAN_CATEGORY:
            categories[key] = value
    company_cats = company.get("categories")
    if isinstance(company_cats, dict):
        for key, value in company_cats.items():
            if key != ZHONGRUAN_CATEGORY:
                categories[key] = value
    if "tools" not in categories:
        categories["tools"] = {"en": "Tools & Capabilities", "zh": "工具与能力"}

    pinned = pin_company_plugins(company_plugins, official_plugins)
    plugins = pinned + official_plugins
    return {
        "name": str(company.get("name") or "company-dsh-plugins"),
        "url": str(company.get("url") or ""),
        "updated": _today(),
        "count": len(plugins),
        "categories": categories,
        "plugins": plugins,
        "workbuddy_merge": {
            "company_count": len(pinned),
            "official_count": len(official_plugins),
        },
    }


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh: Any = None

    def __enter__(self) -> FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._fh is not None:
            if fcntl is not None:
                try:
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            self._fh.close()
            self._fh = None


def http_bytes(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        cl = resp.headers.get("Content-Length")
        if cl and str(cl).isdigit() and int(cl) > HTTP_MAX_BYTES:
            raise RuntimeError("response too large")
        raw = resp.read(HTTP_MAX_BYTES + 1)
        if len(raw) > HTTP_MAX_BYTES:
            raise RuntimeError("response too large")
        return raw


def http_json(url: str, timeout: float) -> Any:
    raw = http_bytes(url, timeout)
    return json.loads(raw.decode("utf-8"))


def fetch_official_from_npm(registry: str, timeout: float) -> dict[str, Any]:
    meta_url = f"{registry.rstrip('/')}/{CATALOG_PACKAGE}/latest"
    meta = http_json(meta_url, timeout)
    dist = meta.get("dist") if isinstance(meta, dict) else None
    tarball = dist.get("tarball") if isinstance(dist, dict) else None
    if not isinstance(tarball, str) or not tarball:
        raise RuntimeError("npm catalog packument has no dist.tarball")
    blob = http_bytes(tarball, timeout)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        names = set(tf.getnames())
        for wanted in ("package/plugins.json", "package/data/plugins.json"):
            if wanted not in names:
                continue
            member = tf.getmember(wanted)
            if not member.isfile() or member.issym() or member.islnk():
                continue
            fh = tf.extractfile(member)
            if fh is None:
                continue
            data = json.loads(fh.read().decode("utf-8"))
            if catalog_usable(data):
                return data
    raise RuntimeError("npm catalog tarball missing plugins.json")


def fetch_official_catalog(url: str, npm_registry: str, timeout: float) -> dict[str, Any]:
    errors: list[str] = []
    for candidate in (url,):
        try:
            data = http_json(candidate, timeout)
            if catalog_usable(data):
                return data
            errors.append(f"{candidate}: not a catalog")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
            errors.append(f"{candidate}: {exc}")
    try:
        return fetch_official_from_npm(npm_registry, timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError, tarfile.TarError, RuntimeError) as exc:
        errors.append(f"npm:{npm_registry}: {exc}")
    raise RuntimeError(" ; ".join(errors))


def load_seed(root: Path) -> dict[str, Any]:
    path = root / "apps" / "zr-workbuddy" / "config" / "company-dsh-plugins.seed.json"
    data = load_json(path)
    if catalog_usable(data):
        return data  # type: ignore[return-value]
    raise RuntimeError(f"公司插件种子不可用: {path}")


def overlay_seed_plugins(company: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    """远端/缓存公司目录为主；本仓 seed 补缺失条目（如尚未上架的 @zhongruan/dsh-knowledge）。"""
    out = dict(company)
    plugins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for plugin in company.get("plugins") or []:
        if not isinstance(plugin, dict):
            continue
        key = plugin_identity(plugin)
        if not key or key in seen:
            continue
        seen.add(key)
        plugins.append(plugin)
    added = 0
    for plugin in seed.get("plugins") or []:
        if not isinstance(plugin, dict):
            continue
        key = plugin_identity(plugin)
        if not key or key in seen:
            continue
        seen.add(key)
        plugins.append(dict(plugin))
        added += 1
    out["plugins"] = plugins
    if added:
        out["updated"] = _today()
        print(f"公司目录已叠加 seed 缺失插件 +{added}", file=sys.stderr)
    # 分类：seed 里多出来的 key 并入（zhongruan 仍由 merge_catalogs 保证）
    cats: dict[str, Any] = {}
    for src in (company.get("categories"), seed.get("categories")):
        if isinstance(src, dict):
            for key, value in src.items():
                if key not in cats:
                    cats[key] = value
    if cats:
        out["categories"] = cats
    out["count"] = len(plugins)
    return out


def resolve_company_catalog(root: Path, cache_dir: Path, company_url: str) -> dict[str, Any]:
    company_path = cache_dir / "company.json"
    seed = load_seed(root)
    base: dict[str, Any] | None = None
    try:
        live = http_json(company_url, COMPANY_TIMEOUT_S)
        if catalog_usable(live):
            base = live  # type: ignore[assignment]
        else:
            print("公司目录响应不可用，沿用缓存/种子", file=sys.stderr)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"公司目录拉取失败（不影响已有公司插件）: {exc}", file=sys.stderr)
    if base is None:
        cached = load_json(company_path)
        if catalog_usable(cached):
            base = cached  # type: ignore[assignment]
    if base is None:
        atomic_write_json(company_path, seed)
        return seed
    merged_company = overlay_seed_plugins(base, seed)
    atomic_write_json(company_path, merged_company)
    return merged_company


def load_meta(cache_dir: Path) -> dict[str, Any]:
    data = load_json(cache_dir / "official.meta.json")
    return data if isinstance(data, dict) else {}


def should_refresh_official(meta: dict[str, Any], now: float | None = None) -> bool:
    ts = time.time() if now is None else now
    ok_at = float(meta.get("official_ok_at") or 0)
    attempt_at = float(meta.get("official_last_attempt_at") or 0)
    if ts - ok_at < OFFICIAL_TTL_S:
        return False
    if ts - attempt_at < OFFICIAL_FAIL_BACKOFF_S:
        return False
    return True


def write_merged(cache_dir: Path, company: dict[str, Any], official: dict[str, Any] | None) -> dict[str, Any]:
    merged = merge_catalogs(company, official if catalog_usable(official) else None)
    atomic_write_json(cache_dir / "merged.json", merged)
    return merged


def load_official_cache(cache_dir: Path) -> dict[str, Any] | None:
    data = load_json(cache_dir / "official.json")
    return data if catalog_usable(data) else None


class Paths:
    def __init__(self, root: Path, cache_dir: Path) -> None:
        self.root = root
        self.cache_dir = cache_dir
        self.lock = cache_dir / "merge.lock"
        self.merged = cache_dir / "merged.json"
        self.meta = cache_dir / "official.meta.json"


def cmd_write(paths: Paths, args: argparse.Namespace) -> int:
    company_url = args.company_url
    with FileLock(paths.lock):
        company = resolve_company_catalog(paths.root, paths.cache_dir, company_url)
        official = load_official_cache(paths.cache_dir)
        merged = write_merged(paths.cache_dir, company, official)
    dest = Path(args.out) if args.out else paths.merged
    if dest.resolve() != paths.merged.resolve():
        atomic_write_json(dest, merged)
    print(f"wrote {dest} company={merged['workbuddy_merge']['company_count']} official={merged['workbuddy_merge']['official_count']}", file=sys.stderr)
    return 0


def cmd_refresh_official(paths: Paths, args: argparse.Namespace) -> int:
    meta = load_meta(paths.cache_dir)
    if not args.force and not should_refresh_official(meta):
        print("官方目录仍在 TTL 内，跳过", file=sys.stderr)
        return 0
    meta = dict(meta)
    meta["official_last_attempt_at"] = time.time()
    try:
        official = fetch_official_catalog(args.official_url, args.npm_registry, OFFICIAL_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — 后台刷新必须吞掉，不能影响公司插件
        meta["official_last_error"] = str(exc)
        atomic_write_json(paths.meta, meta)
        print(f"官方目录同步失败（公司插件不受影响）: {exc}", file=sys.stderr)
        return 0
    meta["official_ok_at"] = time.time()
    meta["official_last_error"] = ""
    with FileLock(paths.lock):
        atomic_write_json(paths.cache_dir / "official.json", official)
        atomic_write_json(paths.meta, meta)
        company = resolve_company_catalog(paths.root, paths.cache_dir, args.company_url)
        write_merged(paths.cache_dir, company, official)
    print(f"官方目录已同步 plugins={len(official.get('plugins') or [])}", file=sys.stderr)
    return 0


def _health_payload(cache_dir: Path) -> dict[str, Any]:
    return {"ok": True, "service": SERVICE_NAME, "cache": str(cache_dir.resolve())}


def is_our_server(port: int, cache_dir: Path, timeout: float = 0.4) -> bool:
    try:
        raw = http_bytes(f"http://127.0.0.1:{port}/health", timeout)
        data = json.loads(raw.decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("service") == SERVICE_NAME and data.get("cache") == str(cache_dir.resolve())


def port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def pick_port(preferred: int, cache_dir: Path) -> int | None:
    for port in range(preferred, preferred + 20):
        if is_our_server(port, cache_dir):
            return port
        if port_free(port):
            return port
    return None


def make_handler(merged_path: Path, cache_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/health",):
                body = json.dumps(_health_payload(cache_dir), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path in ("/", "/plugins.json"):
                try:
                    body = merged_path.read_bytes()
                except OSError:
                    self.send_error(503, "merged catalog missing")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    return Handler


def cmd_serve(paths: Paths, args: argparse.Namespace) -> int:
    if not paths.merged.is_file():
        print("缺少 merged.json，请先 ensure/write", file=sys.stderr)
        return 1
    handler = make_handler(paths.merged, paths.cache_dir)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"serving http://127.0.0.1:{args.port}/plugins.json", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


def spawn_background(argv: list[str], log_path: Path) -> None:
    import subprocess

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "ab", buffering=0)
    try:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log_f.close()


def cmd_ensure(paths: Paths, args: argparse.Namespace) -> int:
    with FileLock(paths.lock):
        company = resolve_company_catalog(paths.root, paths.cache_dir, args.company_url)
        official = load_official_cache(paths.cache_dir)
        merged = write_merged(paths.cache_dir, company, official)
    print(
        f"merged company={merged['workbuddy_merge']['company_count']} official={merged['workbuddy_merge']['official_count']}",
        file=sys.stderr,
    )

    meta = load_meta(paths.cache_dir)
    if should_refresh_official(meta):
        spawn_background(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "refresh-official",
                "--root",
                str(paths.root),
                "--cache-dir",
                str(paths.cache_dir),
                "--company-url",
                args.company_url,
                "--official-url",
                args.official_url,
                "--npm-registry",
                args.npm_registry,
            ],
            paths.cache_dir / "official-refresh.log",
        )
        print("已后台同步官方目录（每天最多一次）", file=sys.stderr)

    port = pick_port(args.port, paths.cache_dir)
    if port is None:
        print("合并目录端口都被占用，回退公司原 URL", file=sys.stderr)
        return 2
    if not is_our_server(port, paths.cache_dir):
        spawn_background(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "serve",
                "--root",
                str(paths.root),
                "--cache-dir",
                str(paths.cache_dir),
                "--port",
                str(port),
            ],
            paths.cache_dir / "httpd.log",
        )
        for _ in range(25):
            time.sleep(0.08)
            if is_our_server(port, paths.cache_dir):
                break
        else:
            print("合并目录服务未起来，回退公司原 URL", file=sys.stderr)
            return 2
    url = f"http://127.0.0.1:{port}/plugins.json"
    print(f"DSHM_REGISTRY_URL={url}")
    return 0


def default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_cache_dir() -> Path:
    home = os.environ.get("DSH_HOME") or str(Path.home() / ".dsh")
    return Path(home) / "market-merge"


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=default_root())
    p.add_argument("--cache-dir", type=Path, default=None)
    p.add_argument("--company-url", default=os.environ.get("COMPANY_DSH_MARKET_URL") or DEFAULT_COMPANY_URL)
    p.add_argument("--official-url", default=os.environ.get("OFFICIAL_DSH_MARKET_URL") or DEFAULT_OFFICIAL_URL)
    p.add_argument("--npm-registry", default=os.environ.get("DSHM_NPM_MIRROR") or DEFAULT_NPM_REGISTRY)
    p.add_argument("--port", type=int, default=int(os.environ.get("WORKBUDDY_MARKET_MERGE_PORT") or DEFAULT_PORT))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="合并公司与官方 DSH 插件目录")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="写出合并目录（可供公司站 nginx 使用）")
    add_common_args(w)
    w.add_argument("--out", default="")
    r = sub.add_parser("refresh-official", help="若超过 TTL 则拉取官方目录")
    add_common_args(r)
    r.add_argument("--force", action="store_true")
    s = sub.add_parser("serve", help="在 127.0.0.1 提供 merged.json")
    add_common_args(s)
    e = sub.add_parser("ensure", help="写合并目录、按需后台同步官方、启动回环服务")
    add_common_args(e)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cache_dir = args.cache_dir or default_cache_dir()
    paths = Paths(args.root.resolve(), cache_dir.expanduser().resolve())
    paths.cache_dir.mkdir(parents=True, exist_ok=True)
    if args.cmd == "write":
        return cmd_write(paths, args)
    if args.cmd == "refresh-official":
        return cmd_refresh_official(paths, args)
    if args.cmd == "serve":
        return cmd_serve(paths, args)
    if args.cmd == "ensure":
        return cmd_ensure(paths, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
