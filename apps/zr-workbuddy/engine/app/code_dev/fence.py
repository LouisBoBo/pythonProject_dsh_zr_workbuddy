"""解析 :::cursor_dev_options / :::cursor_dev_propose 机器块（对齐 simplified 围栏语法）。"""
from __future__ import annotations

import json
import re
from typing import Any

_OPT_RE = re.compile(r":::cursor_dev_options\b", re.I)
_PROP_RE = re.compile(r":::cursor_dev_propose\b", re.I)


def _extract_fence(text: str, kind: str) -> tuple[str, str, str] | None:
    """返回 (before, body_json, after) 或 None。"""
    s = text or ""
    start_re = _OPT_RE if kind == "options" else _PROP_RE
    m = start_re.search(s)
    if not m:
        return None
    start = m.start()
    after_tag = s[m.end() :]
    body_begin = len(after_tag) - len(after_tag.lstrip())
    body_and_rest = after_tag[body_begin:]
    close = re.search(r"\n[ \t]*:::[ \t]*(?:\n|$)", body_and_rest)
    if close:
        body = body_and_rest[: close.start()].strip()
        end = m.end() + body_begin + close.end()
    else:
        body = re.sub(r"\n?[ \t]*:::[ \t]*\s*$", "", body_and_rest).strip()
        end = len(s)
    return s[:start].strip(), body, s[end:].strip()


def _loads_loose(body: str) -> dict[str, Any] | None:
    raw = (body or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        # 尝试截取首尾花括号
        a, b = raw.find("{"), raw.rfind("}")
        if a >= 0 and b > a:
            try:
                obj = json.loads(raw[a : b + 1])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def parse_machine_blocks(text: str) -> dict[str, Any]:
    """返回 {prose, options, propose}；同一轮优先 options（禁止双卡时前端只展示一张）。"""
    s = text or ""
    options = None
    propose = None
    prose_parts: list[str] = []

    # 若同时出现，按文档：不应同时有；仍优先 options
    opt = _extract_fence(s, "options")
    prop = _extract_fence(s, "propose")
    if opt and prop:
        # 保留较早出现的那一类
        if opt[0] is not None and (not prop or s.find(":::cursor_dev_options") <= s.lower().find(":::cursor_dev_propose")):
            before, body, after = opt
            options = _loads_loose(body)
            prose_parts.append(before)
            prose_parts.append(after)
            # 去掉 propose 段避免泄漏
            prop2 = _extract_fence("\n".join(prose_parts), "propose")
            if prop2:
                prose_parts = [prop2[0], prop2[2]]
        else:
            before, body, after = prop
            propose = _loads_loose(body)
            prose_parts.append(before)
            prose_parts.append(after)
    elif opt:
        before, body, after = opt
        options = _loads_loose(body)
        prose_parts.extend([before, after])
    elif prop:
        before, body, after = prop
        propose = _loads_loose(body)
        prose_parts.extend([before, after])
    else:
        prose_parts.append(s)

    prose = "\n\n".join(p for p in prose_parts if p).strip()
    # 再清残留围栏字样
    prose = re.sub(r":::cursor_dev_\w+", "", prose).strip()
    return {"prose": prose, "options": options, "propose": propose}
