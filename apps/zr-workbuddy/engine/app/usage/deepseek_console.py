"""DeepSeek 官网日用量对照：平台拉取 或 手工录入（别人认的数字）。

公开 API 无按日 Token。可：
1) usage.deepseek_platform_token → 拉 platform.deepseek.com
2) 手工 POST / 写入 data/usage/console_days.json（从控制台抄当日次数/Token/金额）
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_LOG = logging.getLogger(__name__)
_TZ = ZoneInfo("Asia/Shanghai")
_ENGINE_ROOT = Path(__file__).resolve().parents[2]
_cache: dict[str, Any] = {"at": 0.0, "key": "", "payload": None}
_CACHE_SEC = 60.0


def _usage_cfg() -> dict[str, Any]:
    try:
        from ..config_store import load_config

        cfg = load_config().get("usage") or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _token() -> str:
    cfg = _usage_cfg()
    if cfg.get("deepseek_platform_enabled") is False:
        return ""
    return str(cfg.get("deepseek_platform_token") or "").strip()


def _day_from_on(on: str) -> str:
    text = str(on or "").strip()[:10]
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _console_path() -> Path:
    try:
        from . import store as st

        return Path(st._dir()) / "console_days.json"
    except Exception:
        return _ENGINE_ROOT / "data" / "usage" / "console_days.json"


def load_manual_days() -> dict[str, Any]:
    path = _console_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def save_manual_day(
    *,
    day: str,
    calls: int,
    tokens: int,
    cost_cny: float = 0.0,
    note: str = "",
) -> dict[str, Any]:
    """手工录入控制台当日数字（与官网截图一致即可）。"""
    d = _day_from_on(day)
    path = _console_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = str(path) + ".lock"
    row = {
        "day": d,
        "calls": max(0, int(calls)),
        "tokens": max(0, int(tokens)),
        "cost_cny": round(float(cost_cny or 0), 4),
        "source": "manual",
        "note": (note or "手工录入，与 DeepSeek 控制台截图对齐")[:200],
        "updated_at": datetime.now(_TZ).isoformat(timespec="seconds"),
    }
    with open(lock, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            data = load_manual_days()
            data[d] = row
            tmp = str(path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    return {"ok": True, **row, "configured": True}


def _manual_day(day: str) -> dict[str, Any] | None:
    row = load_manual_days().get(day)
    if not isinstance(row, dict):
        return None
    return {
        "ok": True,
        "configured": True,
        "day": day,
        "calls": int(row.get("calls") or 0),
        "tokens": int(row.get("tokens") or 0),
        "cost_cny": float(row.get("cost_cny") or 0),
        "source": "manual",
        "note": str(row.get("note") or "手工录入（与控制台同口径）"),
    }


def _pick_day_row(rows: Any, day: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("date", "day", "stat_date", "statDate", "time", "dt"):
            raw = str(row.get(key) or "")
            if day in raw or raw.startswith(day):
                return row
            try:
                n = float(raw)
                if n > 1e12:
                    n /= 1000.0
                if n > 1e9:
                    ds = datetime.fromtimestamp(n, tz=_TZ).strftime("%Y-%m-%d")
                    if ds == day:
                        return row
            except (TypeError, ValueError, OSError):
                pass
    return None


def _num(row: dict[str, Any], *keys: str) -> float:
    for k in keys:
        if k not in row:
            continue
        try:
            return float(row.get(k) or 0)
        except (TypeError, ValueError):
            continue
    return 0.0


def _normalize_day(row: dict[str, Any] | None, day: str, *, cost_cny: float | None = None) -> dict[str, Any]:
    if not row:
        return {
            "ok": True,
            "configured": True,
            "day": day,
            "calls": 0,
            "tokens": 0,
            "cost_cny": float(cost_cny or 0),
            "source": "deepseek_platform",
            "note": "控制台当日无明细或接口字段变更",
        }
    calls = int(
        _num(
            row,
            "request_count",
            "requestCount",
            "api_count",
            "apiCount",
            "count",
            "requests",
            "call_count",
        )
    )
    tokens = int(
        _num(
            row,
            "total_tokens",
            "totalTokens",
            "token_count",
            "tokenCount",
            "tokens",
        )
    )
    cny = cost_cny
    if cny is None:
        cny = _num(row, "cost", "cost_cny", "costCny", "consume_amount", "consumeAmount", "money")
        if tokens == 0 and 0 < _num(row, "amount") < 1_000_000:
            cny = _num(row, "amount")
    return {
        "ok": True,
        "configured": True,
        "day": day,
        "calls": calls,
        "tokens": tokens,
        "cost_cny": round(float(cny or 0), 4),
        "source": "deepseek_platform",
        "note": "与 DeepSeek 控制台同口径（Key 全量）",
    }


def _fetch_platform(day: str) -> dict[str, Any]:
    token = _token()
    if not token:
        return {
            "ok": False,
            "configured": False,
            "day": day,
            "detail": "未配置 usage.deepseek_platform_token",
        }
    cache_key = f"plat:{day}:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
    now = time.monotonic()
    if (
        _cache.get("key") == cache_key
        and _cache.get("payload") is not None
        and now - float(_cache.get("at") or 0) < _CACHE_SEC
    ):
        return dict(_cache["payload"])

    year = int(day[:4])
    month = int(day[5:7])
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "ZR-WorkBuddy-usage-reconcile/1.0",
    }
    amount_rows: Any = None
    cost_rows: Any = None
    err = ""
    try:
        import httpx

        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            for path, bucket in (
                ("/api/v0/usage/amount", "amount"),
                ("/api/v0/usage/cost", "cost"),
            ):
                url = "https://platform.deepseek.com" + path
                try:
                    r = client.get(url, params={"year": year, "month": month}, headers=headers)
                except Exception as ex:
                    err = str(ex)[:160]
                    continue
                if r.status_code >= 400:
                    err = f"HTTP {r.status_code}"
                    continue
                try:
                    body = r.json()
                except Exception:
                    err = "非 JSON 响应"
                    continue
                if isinstance(body, dict):
                    code = body.get("code")
                    if code not in (None, 0, "0", 200, "200"):
                        err = str(body.get("msg") or body.get("message") or f"code={code}")[:160]
                        continue
                    data = body.get("data", body)
                else:
                    data = body
                if bucket == "amount":
                    amount_rows = data if isinstance(data, list) else (
                        data.get("list") or data.get("items") or data.get("days") if isinstance(data, dict) else data
                    )
                else:
                    cost_rows = data if isinstance(data, list) else (
                        data.get("list") or data.get("items") or data.get("days") if isinstance(data, dict) else data
                    )
    except Exception:
        _LOG.warning("deepseek console fetch failed", exc_info=True)
        return {"ok": False, "configured": True, "day": day, "detail": "拉取控制台失败"}

    amount_row = _pick_day_row(amount_rows, day)
    cost_row = _pick_day_row(cost_rows, day)
    cost_cny = None
    if cost_row:
        cost_cny = _num(cost_row, "cost", "cost_cny", "costCny", "amount", "consume_amount", "money")
    if not amount_row and not cost_row:
        payload = {
            "ok": False,
            "configured": True,
            "day": day,
            "detail": err or "控制台未返回当日明细（token 可能过期）",
        }
        _cache.update({"at": now, "key": cache_key, "payload": payload})
        return payload

    base = dict(amount_row or {})
    if cost_row:
        for k, v in cost_row.items():
            if k not in base or base.get(k) in (None, "", 0, "0"):
                base[k] = v
    payload = _normalize_day(base, day, cost_cny=cost_cny)
    if payload["tokens"] == 0 and isinstance(amount_row, dict):
        nested = amount_row.get("usage") or amount_row.get("stats")
        if isinstance(nested, dict):
            payload["tokens"] = int(_num(nested, "total_tokens", "totalTokens", "tokens"))
            if payload["calls"] == 0:
                payload["calls"] = int(_num(nested, "request_count", "requestCount", "count"))
    _cache.update({"at": now, "key": cache_key, "payload": payload})
    return payload


def fetch_console_day(
    on: str = "",
    local: dict[str, Any] | None = None,
    *,
    allow_platform: bool = True,
) -> dict[str, Any]:
    """优先手工录入 →（可选）平台拉取；附带与本机账本的差额说明。

    allow_platform=False 时不调 Key 账单接口（非管理员个人用量页），仅返回手工录入。
    """
    day = _day_from_on(on)
    manual = _manual_day(day)
    if manual and manual.get("ok"):
        out = dict(manual)
    elif allow_platform:
        plat = _fetch_platform(day)
        if plat.get("ok"):
            out = dict(plat)
        else:
            out = {
                "ok": False,
                "configured": bool(_token()) or bool(load_manual_days().get(day)),
                "day": day,
                "detail": plat.get("detail")
                or "未配置官网对照：可在用量页录入控制台当日数字，或填 deepseek_platform_token",
                "hint": "DeepSeek 控制台 → 选当日 → 把「请求次数 / Tokens / 金额」录入本机；"
                "本机账本不含记忆插件未落盘的真值 token，无法自行凑齐官网总额。",
            }
    else:
        has_manual = bool(load_manual_days().get(day))
        out = {
            "ok": False,
            "configured": has_manual,
            "day": day,
            "detail": "未录入当日控制台数字（平台 Key 拉取仅管理员可用）"
            if not has_manual
            else "手工录入不可用",
            "hint": "请管理员在用量页录入控制台当日数字，或使用企业用量视图。",
        }

    # 差额（相对本机 LLM 当日）
    if local and isinstance(local, dict):
        llm = local.get("llm") if isinstance(local.get("llm"), dict) else {}
        loc_calls = int(llm.get("calls") or local.get("llm_calls") or 0)
        loc_tok = int(llm.get("tokens") or local.get("llm_tokens") or 0)
        if out.get("ok"):
            out["local_calls"] = loc_calls
            out["local_tokens"] = loc_tok
            out["gap_calls"] = int(out.get("calls") or 0) - loc_calls
            out["gap_tokens"] = int(out.get("tokens") or 0) - loc_tok
            out["reconcile_note"] = (
                "官网=Key 全量计费；本机=可观测流水（含部分估算）。"
                "差额多为记忆/抽取等未回传 usage 的调用，以官网为准。"
            )
    return out
