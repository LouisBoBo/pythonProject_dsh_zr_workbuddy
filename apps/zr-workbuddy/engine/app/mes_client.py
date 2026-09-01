"""MES/ERP 直连客户端：登录（JWT）、token 缓存、接口调用、连通性探测。"""

from __future__ import annotations

import base64
import time
from typing import Any, Dict

import httpx

_token: str | None = None
_token_at: float = 0.0


class MesError(Exception):
    pass


def _extra_headers(cfg_mes: dict) -> dict:
    try:
        import json

        h = json.loads(cfg_mes.get("extra_headers") or "{}")
        return h if isinstance(h, dict) else {}
    except Exception:
        return {}


async def probe_connection(cfg_mes: dict) -> Dict[str, Any]:
    """统一 MES 连通性探测（面板 HTTP / CLI / Agent 共用，禁止分叉实现）。"""
    url = (cfg_mes.get("base_url") or "").strip().rstrip("/")
    if not url:
        return {"ok": False, "detail": "未配置 MES 连接地址（base_url 为空）"}

    headers = _extra_headers(cfg_mes)
    auth_type = cfg_mes.get("auth_type", "password")
    if auth_type == "password" and cfg_mes.get("username"):
        token_b64 = base64.b64encode(
            f"{cfg_mes.get('username', '')}:{cfg_mes.get('password', '')}".encode()
        ).decode()
        headers.setdefault("Authorization", f"Basic {token_b64}")
    elif auth_type == "token" and cfg_mes.get("token"):
        headers.setdefault("Authorization", f"Bearer {cfg_mes['token']}")
    elif auth_type == "apikey" and cfg_mes.get("token"):
        headers.setdefault("X-API-Key", cfg_mes["token"])

    try:
        async with httpx.AsyncClient(
            verify=bool(cfg_mes.get("verify_ssl", True)),
            timeout=float(cfg_mes.get("timeout") or 30),
            follow_redirects=True,
        ) as client:
            r = await client.get(url, headers=headers)
            reachable = f"服务器可达（HTTP {r.status_code}）"
            if r.status_code == 404:
                reachable = "服务器可达（根路径无页面，正常）"

            if auth_type == "password" and cfg_mes.get("username") and "/api/auth/login" not in url:
                lr = await client.post(
                    url + "/api/auth/login",
                    json={
                        "username": cfg_mes.get("username"),
                        "password": cfg_mes.get("password"),
                        "enterprise_code": cfg_mes.get("enterprise_code") or "江西中软",
                    },
                )
                if lr.status_code == 200:
                    try:
                        body = lr.json()
                    except Exception:
                        body = {}
                    if body.get("access_token") or body.get("token"):
                        return {
                            "ok": True,
                            "detail": f"{reachable}，且登录成功（账号验证通过）",
                            "base_url": url,
                        }
                return {
                    "ok": False,
                    "detail": f"{reachable}，但登录失败（HTTP {lr.status_code}）：{lr.text[:150]}",
                    "base_url": url,
                }
            return {"ok": True, "detail": reachable, "base_url": url}
    except Exception as e:
        return {"ok": False, "detail": f"连接失败：{type(e).__name__}: {e}", "base_url": url}


async def login(cfg_mes: dict) -> str:
    global _token, _token_at
    base = (cfg_mes.get("base_url") or "").strip().rstrip("/")
    payload = {
        "username": cfg_mes.get("username") or "",
        "password": cfg_mes.get("password") or "",
        "enterprise_code": cfg_mes.get("enterprise_code") or "江西中软",
    }
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(base + "/api/auth/login", json=payload)
        if r.status_code != 200:
            raise MesError(f"MES 登录失败(HTTP {r.status_code}): {r.text[:200]}")
        data = r.json()
        tok = data.get("access_token") or data.get("token")
        if not tok:
            raise MesError(f"MES 登录响应缺少 token: {str(data)[:200]}")
        _token, _token_at = tok, time.time()
        return tok


async def get_token(cfg_mes: dict) -> str:
    global _token, _token_at
    if _token and time.time() - _token_at < 3000:
        return _token
    return await login(cfg_mes)


async def api_get(cfg_mes: dict, path: str, params: dict | None = None):
    global _token
    base = (cfg_mes.get("base_url") or "").strip().rstrip("/")

    async def _do(c: httpx.AsyncClient, token: str):
        return await c.get(base + path, params=params,
                           headers={"Authorization": f"Bearer {token}"})

    async with httpx.AsyncClient(timeout=20) as c:
        r = await _do(c, await get_token(cfg_mes))
        if r.status_code == 401:
            _token = None  # token 失效，强制重新登录
            r = await _do(c, await get_token(cfg_mes))
        if r.status_code != 200:
            raise MesError(f"GET {path} 失败(HTTP {r.status_code}): {r.text[:200]}")
        return r.json()


async def fetch_daily_output(cfg_mes: dict, date_from: str = "", date_to: str = "",
                             line: str = "") -> list:
    """分页拉取日产量报表（页大小 100，循环至取完）。"""
    rows, page = [], 1
    while True:
        params = {"page": page, "page_size": 100}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if line:
            params["production_line"] = line
        d = await api_get(cfg_mes, "/api/reports/daily-output", params)
        items = d.get("items") or []
        rows.extend(items)
        if len(items) < 100 or page >= 20:
            break
        page += 1
    return rows
