"""本机 Cursor SDK Local Agent（沙箱 cwd）；改编自 simplified local_dev，去掉 Cloud/stack_chain 依赖。"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable

from .config import availability as config_availability
from .config import get_config

Sink = Callable[[dict[str, Any]], None]

_USAGE_LIMIT_RE = re.compile(
    r"out of usage|usage limit|increase your limit|you're out of usage",
    re.I,
)


def _emit(sink: Sink | None, event: dict[str, Any]) -> None:
    if sink:
        try:
            sink(event)
        except Exception:
            pass


def _local_agent_options(cwd: str):
    from cursor_sdk import LocalAgentOptions, LocalAgentStoreConfig, SandboxOptions  # type: ignore

    store_root = str(Path(cwd) / ".cursor-sdk-store")
    Path(store_root).mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "setting_sources": [],
        "sandbox_options": SandboxOptions(enabled=True),
        "store": LocalAgentStoreConfig(type="sqlite", root_dir=store_root),
    }
    try:
        return LocalAgentOptions(**kwargs)
    except TypeError:
        kwargs.pop("store", None)
        try:
            return LocalAgentOptions(**kwargs)
        except TypeError:
            return LocalAgentOptions(cwd=cwd, sandbox_options=SandboxOptions(enabled=True))


def _sdk_message_fields(message: Any) -> tuple[str, str, str]:
    mtype = str(
        getattr(message, "type", None)
        or (message.get("type") if isinstance(message, dict) else None)
        or ""
    )
    status = str(
        getattr(message, "status", None)
        or (message.get("status") if isinstance(message, dict) else None)
        or ""
    )
    raw_msg = getattr(message, "message", None)
    if raw_msg is None and isinstance(message, dict):
        raw_msg = message.get("message")
    msg = raw_msg if isinstance(raw_msg, str) else ""
    return mtype, status, msg.strip()


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _short_text(value: Any, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _content_blocks_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, (list, tuple)):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") in (None, "text", "output_text"):
                parts.append(str(block.get("text") or ""))
            continue
        btype = getattr(block, "type", None)
        if btype in (None, "text", "output_text"):
            t = getattr(block, "text", None)
            if t:
                parts.append(str(t))
    return "".join(parts)


def _thinking_from_message(message: Any) -> tuple[str, int | None]:
    """从 Cursor SDK thinking 事件取出正文与耗时（毫秒）。"""
    text = getattr(message, "text", None)
    if not text and isinstance(message, dict):
        text = message.get("text")
    if not text:
        inner = getattr(message, "message", None)
        if isinstance(inner, dict):
            text = inner.get("text")
        elif inner is not None:
            text = getattr(inner, "text", None)
    dur = getattr(message, "thinking_duration_ms", None)
    if dur is None:
        dur = getattr(message, "thinkingDurationMs", None)
    if dur is None and isinstance(message, dict):
        dur = message.get("thinking_duration_ms") or message.get("thinkingDurationMs")
    dur_i: int | None = None
    if dur is not None:
        try:
            dur_i = max(0, int(dur))
        except (TypeError, ValueError):
            dur_i = None
    return str(text or ""), dur_i


def _assistant_text_from_message(message: Any) -> str:
    text = getattr(message, "text", None)
    if text:
        return str(text)
    if isinstance(message, dict):
        nested = message.get("message")
        if isinstance(nested, dict):
            got = _content_blocks_text(nested.get("content")) or str(nested.get("text") or "")
            if got:
                return got
        got = _content_blocks_text(message.get("content"))
        if got:
            return got
        return str(message.get("text") or "")
    inner = getattr(message, "message", None)
    if inner is not None:
        got = _content_blocks_text(getattr(inner, "content", None))
        if got:
            return got
        t = getattr(inner, "text", None)
        if t:
            return str(t)
        if isinstance(inner, dict):
            got = _content_blocks_text(inner.get("content")) or str(inner.get("text") or "")
            if got:
                return got
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    return _content_blocks_text(content)


def _tool_args(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        nested = value.get("args") or value.get("arguments") or value.get("params") or value.get("input")
        if isinstance(nested, dict):
            return nested
        return value
    return {}


_TOOL_NAME_ALIAS = {
    "read": "Read",
    "write": "Write",
    "strreplace": "StrReplace",
    "searchreplace": "StrReplace",
    "grep": "Grep",
    "shell": "Shell",
    "ls": "LS",
    "glob": "Glob",
    "edit": "StrReplace",
    "semsearch": "SemanticSearch",
    "semanticsearch": "SemanticSearch",
}


def _pretty_tool_name(name: str) -> str:
    raw = (name or "").strip()
    key = re.sub(r"[^a-z]", "", raw.lower())
    if key.endswith("toolcall"):
        key = key[: -len("toolcall")]
    return _TOOL_NAME_ALIAS.get(key, raw or "工具")


def _public_relpath(raw: str, sandbox: str = "") -> str:
    """把沙箱/工程绝对路径收成短相对路径，避免刷屏。"""
    p = (raw or "").strip().replace("\\", "/")
    if not p:
        return ""
    sb = (sandbox or "").strip().replace("\\", "/").rstrip("/")
    if sb and (p == sb or p.startswith(sb + "/")):
        rel = p[len(sb) :].lstrip("/")
        return "" if rel in {"", "."} else rel
    m = re.search(r"/sandboxes/ldj-[a-f0-9]+/(.*)$", p, re.I)
    if m:
        return (m.group(1) or "").strip("/")
    m = re.search(r"/pythonProject_zr_aicoding/(.*)$", p)
    if m:
        return (m.group(1) or "").strip("/")
    if "/DSH-ZR-WorkBuddy/" in p and "/sandboxes/" not in p:
        return ""
    if p.startswith("/") or re.match(r"^[A-Za-z]:/", p):
        name = Path(p).name
        return name if name and name not in {".", ".."} else ""
    return p.lstrip("./")


_SANDBOX_ABS_RE = re.compile(
    r"(?:/Users/[^/\s\"']+(?:/[^/\s\"']+)*/)?sandboxes/ldj-[a-f0-9]+/",
    re.I,
)


def _scrub_public_text(text: str, sandbox: str = "") -> str:
    """正文里禁止出现沙箱绝对路径。"""
    t = text or ""
    sb = (sandbox or "").strip().replace("\\", "/").rstrip("/")
    if sb:
        t = t.replace(sb + "/", "").replace(sb, "")
    t = _SANDBOX_ABS_RE.sub("", t)
    t = re.sub(
        r"/Users/[^/\s\"']+/ai_projects/DSH-ZR-WorkBuddy/apps/zr-workbuddy/engine/data/local_dev/sandboxes/ldj-[a-f0-9]+/",
        "",
        t,
    )
    t = re.sub(
        r"The development tool card has been opened for you\.[\s\S]*?in the tool card\.?\s*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"Please complete the directory selection and requirement confirmation in the tool card\.?\s*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"已为您打开写码工具卡[，,][^\n]*[。．]?\s*", "", t)
    return t


def _walk_tool_payload(obj: Any, depth: int = 0) -> tuple[str, dict[str, Any]]:
    if depth > 6 or obj is None:
        return "", {}
    if not isinstance(obj, dict):
        return "", {}
    name = str(obj.get("name") or obj.get("toolName") or obj.get("tool_name") or "").strip()
    if isinstance(obj.get("tool"), str) and not name:
        name = str(obj.get("tool") or "")
    if isinstance(obj.get("tool"), dict) and not name:
        name = str(obj["tool"].get("name") or obj["tool"].get("toolName") or "")
    for key, val in obj.items():
        ks = str(key)
        if ks.endswith("ToolCall") and isinstance(val, dict):
            nested_name, nested_args = _walk_tool_payload(val, depth + 1)
            label = name or ks[: -len("ToolCall")] or nested_name
            args = nested_args or val.get("args") or val.get("arguments") or val
            if not isinstance(args, dict):
                args = val if isinstance(val, dict) else {}
            return _pretty_tool_name(label), args if isinstance(args, dict) else {}
    args = obj.get("args") or obj.get("arguments") or obj.get("params") or obj.get("input")
    if isinstance(args, dict):
        return _pretty_tool_name(name), args
    return _pretty_tool_name(name), obj


def _tool_name_and_args(tool: Any) -> tuple[str, Any]:
    name, args = _walk_tool_payload(tool if isinstance(tool, dict) else {})
    return name, args if isinstance(args, dict) else {}


_TOOL_VERB = {
    "Read": "阅读",
    "Write": "写入",
    "StrReplace": "修改",
    "Grep": "搜索",
    "Shell": "执行",
    "LS": "查看目录",
    "Glob": "查找文件",
    "SemanticSearch": "检索",
}


def _tool_activity_line(*, name: str = "", status: str = "", args: Any = None, extra: str = "", sandbox: str = "") -> str:
    extracted_name, payload = _tool_name_and_args(args) if isinstance(args, dict) else (name, {})
    if not isinstance(payload, dict):
        payload = _tool_args(args) if not isinstance(args, str) else {}
    label = _pretty_tool_name((name or extracted_name or "").strip())
    path = extra
    if not path and isinstance(payload, dict):
        for key in (
            "path",
            "file_path",
            "target_file",
            "filePath",
            "relative_workspace_path",
        ):
            if payload.get(key):
                path = str(payload.get(key) or "")
                break
        if not path and payload.get("command"):
            path = str(payload.get("command") or "")
        if not path and (payload.get("pattern") or payload.get("query") or payload.get("glob_pattern")):
            path = str(payload.get("pattern") or payload.get("query") or payload.get("glob_pattern") or "")
    rel = _public_relpath(path, sandbox)
    if not rel and label in {"工具", ""}:
        return ""
    verb = _TOOL_VERB.get(label, "查看")
    st = (status or "").strip().lower()
    suffix = "（失败）" if st in {"error", "failed"} else ""
    if rel:
        return f"{verb} `{rel}`{suffix}"
    if label and label != "工具":
        return f"{verb}{suffix}"
    return ""


_ACTIVITY_PATH_RE = re.compile(r"`([^`]+)`")
_ACTIVITY_GENERIC = frozenset({"查找文件", "搜索", "查看", "检索", "查看目录", "执行"})


def _activity_path_key(line: str) -> str:
    m = _ACTIVITY_PATH_RE.search(line or "")
    if m:
        return m.group(1).strip().replace("\\", "/")
    bare = (line or "").strip().split("（", 1)[0].strip()
    if bare in _ACTIVITY_GENERIC:
        return ""
    return bare


def _record_activity_line(activity_by_path: dict[str, str], order: list[str], line: str) -> None:
    """同一路径只保留最后一次操作，避免「查看 A → 查看 A」刷屏。"""
    key = _activity_path_key(line)
    if key:
        if key in activity_by_path:
            try:
                order.remove(key)
            except ValueError:
                pass
        activity_by_path[key] = line
        order.append(key)
        return
    # 无路径的泛化动作（查找/搜索）：已有具体文件时不再追加
    if len(activity_by_path) >= 1:
        return
    gkey = f"__generic__:{line}"
    if gkey in activity_by_path:
        return
    activity_by_path[gkey] = line
    order.append(gkey)


_CJK_DUP_RE = re.compile(r"([\u4e00-\u9fff]{2,24}[。．、，：:」』】]?)\1+")
_CJK_GAP_DUP_RE = re.compile(
    r"([\u4e00-\u9fff]{2,16})(?:[\s　]*[。．、，：:.*＊]+[\s　]*)+\1+"
)
_HEADING_DUP_RE = re.compile(
    r"(做了什么|改动文件|行为约定|验收步骤|一句话结论|说明方案|改动)(?:[\s　。．、，：:*＊]+)+\1"
)
_WORD_DUP_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_.]{2,40})\b(?:[\s　]+\1\b)+")
_STUCK_WORD_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]{2,24})\1\b")


def _collapse_phrase_dups(text: str) -> str:
    """去掉「加班管理。加班管理。」「做了什么 。 做了什么」这类紧邻重复。"""
    t = _fix_broken_cjk_punct(text or "")
    for _ in range(8):
        n = _CJK_DUP_RE.sub(r"\1", t)
        n = _CJK_GAP_DUP_RE.sub(r"\1", n)
        n = _HEADING_DUP_RE.sub(r"\1", n)
        n = _WORD_DUP_RE.sub(r"\1", n)
        n = _STUCK_WORD_RE.sub(r"\1", n)
        n = _dedupe_spaced_sentences(n)
        if n == t:
            break
        t = n
    return t


_CODE_LINE_HEAD = re.compile(
    r"^(?:from\s+\w+\s+import|import\s+|class\s+|def\s+|async\s+def|@|#\s|"
    r"if\s+|elif\s+|else:|for\s+|while\s+|return\s+|try:|except|with\s+|"
    r"<\/?[\w-]+|<template|<script|<style|el-[\w-]+)",
    re.I,
)


_STUCK_NEXT = re.compile(
    r"^(from\s|import\s|class\s|def\s|const\s|let\s|var\s|function\s|export\s|"
    r"async\s|return\s|if\s|for\s|while\s|try:|except|with\s|@|<[\w/-]|</)",
    re.I,
)


def _needs_newline_between(left: str, right: str) -> bool:
    """流式增量硬拼接时，在代码行边界补换行（避免 datetimeimport）。"""
    if not left or not right:
        return False
    if left.endswith(("\n", "\r")):
        return False
    r = right.lstrip()
    if not r:
        return False
    tail = left.rstrip().split("\n")[-1]
    if _STUCK_NEXT.match(r) and (left[-1].isalnum() or left[-1] in "\"'`)}>]"):
        return True
    if _line_looks_like_code(tail) or _line_looks_like_code(r):
        if _CODE_LINE_HEAD.match(r):
            return True
        if re.match(r"^[)\]}]", r):
            return True
    if left.rstrip().endswith((":", "{", "(", "[", ",", "\"", "'")) and _line_looks_like_code(r):
        return True
    return False


def _glue_text_chunks(prev: str, incoming: str) -> str:
    """合并文本块；代码行边界自动补换行。"""
    p = prev or ""
    n = incoming or ""
    if not p:
        return n
    if not n:
        return p
    merged = _concat_overlap(p, n)
    if merged == p + n and _needs_newline_between(p, n):
        return p.rstrip() + "\n" + n.lstrip()
    return merged


def _concat_overlap(prev: str, incoming: str) -> str:
    """快照/增量尾部重叠时只接上新的部分，避免「加班管理」连写两遍。"""
    p = prev or ""
    n = incoming or ""
    if not p:
        return n
    if not n:
        return p
    maxk = min(len(p), len(n), 80)
    for k in range(maxk, 7, -1):
        if not p.endswith(n[:k]):
            continue
        # 拒绝在英文单词中间硬拼接（如 Qual + ityOverview → ityOverview 残片）
        if k < len(n) and p[-1].isascii() and p[-1].isalnum() and n[k : k + 1].isascii() and n[k].isalnum():
            continue
        merged = p + n[k:]
        if _needs_newline_between(p, n[k:]):
            return p.rstrip() + "\n" + n[k:].lstrip()
        return merged
    merged = p + n
    if _needs_newline_between(p, n):
        return p.rstrip() + "\n" + n.lstrip()
    return merged


def _dedupe_spaced_sentences(text: str) -> str:
    """去掉「句子A。 句子A。」或空格粘连的整段重复（SDK 增量常见）。"""
    t = re.sub(r"[ \t]+", " ", (text or "").strip())
    if len(t) < 32:
        return t
    parts = re.split(r"(?<=[。！？])", t)
    out: list[str] = []
    for part in parts:
        s = part.strip()
        if not s:
            continue
        if out:
            prev = out[-1].strip()
            if s == prev:
                continue
            if len(s) >= 18 and len(prev) >= 18 and (s in prev or prev in s):
                if len(s) > len(prev):
                    out[-1] = part
                continue
        out.append(part)
    merged = "".join(out)
    # 整段拷贝两次（中间仅空格）
    mid = len(merged) // 2
    if mid >= 24:
        left, right = merged[:mid].strip(), merged[mid:].strip()
        if left and left == right:
            return left
    return merged


def _fix_broken_cjk_punct(text: str) -> str:
    """修复「定位「。」/「。品质概览」这类断句残片。"""
    t = text or ""
    # 「。」单独成对，或「。正文」——去掉开引号后误插的句号
    t = re.sub(r"「[ \t]*。[ \t]*」", "「", t)
    t = re.sub(r"「[ \t]*。[ \t]*", "「", t)
    t = re.sub(r"。[ \t]*\n[ \t]*、", "、", t)
    return t


def _collapse_repeated_prose(text: str) -> str:
    """去掉整段拷贝两次、连续重复段落（仅用于非围栏正文）。"""
    t = _collapse_phrase_dups((text or "").strip())
    if len(t) < 24:
        return t
    for sep in ("\n\n", "\n"):
        parts = [p.strip() for p in t.split(sep) if p.strip()]
        if len(parts) < 2:
            continue
        out: list[str] = []
        for part in parts:
            if out and (
                part == out[-1]
                or (len(part) > 20 and part in out[-1])
                or (len(out[-1]) > 20 and out[-1] in part)
            ):
                if len(part) > len(out[-1]):
                    out[-1] = part
                continue
            out.append(part)
        t = sep.join(out)
    mid = len(t) // 2
    if mid >= 24:
        left, right = t[:mid].strip(), t[mid:].strip()
        if left == right:
            return left
        if t[:mid] == t[mid:]:
            return t[:mid].strip()
    return _collapse_phrase_dups(t)


def _collapse_repeated(text: str) -> str:
    """去重时保留 ``` 围栏内代码换行与缩进，只处理围栏外说明文字；连续相同围栏块去重。"""
    t = (text or "").strip()
    if not t:
        return ""
    if "```" not in t:
        return _collapse_repeated_prose(t)
    bits: list[str] = []
    for kind, chunk in _segment_fences(t):
        piece = (chunk or "").strip()
        if not piece:
            continue
        if kind == "fence":
            if bits and bits[-1] == piece:
                continue
            bits.append(piece)
        else:
            collapsed = _collapse_repeated_prose(piece)
            if collapsed:
                bits.append(collapsed)
    return "\n\n".join(bits).strip()



def _norm_dialog_key(text: str) -> str:
    """去空白/标点噪声后的比对键，用于识别「有空格版」与「无空格版」同句。"""
    s = str(text or "")
    s = s.replace("`", "").replace("「", "").replace("」", "")
    s = s.replace("→", "").replace("—", "").replace("–", "")
    s = re.sub(r"[#*\-\s]+", "", s)
    s = re.sub(r"[：:，,。．！？?；;、·•]+", "", s)
    # 口语虚词不影响同义判断
    for w in ("由", "的", "了", "则", "再"):
        s = s.replace(w, "")
    return s.lower()


def _near_dup_keys(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 10 and len(b) >= 10 and (a in b or b in a):
        return True
    if abs(len(a) - len(b)) <= max(3, len(a) // 10):
        # 简单字符重叠率
        sa, sb = set(a), set(b)
        inter = len(sa & sb)
        union = max(1, len(sa | sb))
        if inter / union >= 0.86:
            return True
    return False


def _expand_glued_delete_plan(text: str) -> str:
    """把「##删除清单-path：说明-path：说明结论：…」展开成可读 Markdown。"""
    t = (text or "").replace("\r\n", "\n")
    m = re.search(r"#{0,3}\s*删除清单", t)
    if not m:
        return t
    head = t[: m.start()].rstrip()
    tail = t[m.end() :]
    conc = re.search(r"结论\s*[：:]", tail)
    plan_body = tail[: conc.start()] if conc else tail
    rest = tail[conc.start() :] if conc else ""
    paths = re.findall(
        r"-?\s*`?((?:frontend|backend|apps|src)/[\w./@-]+\.[A-Za-z0-9]+)`?\s*[：:]?\s*"
        r"([^`\-]*?)(?=(?:-?\s*`?(?:frontend|backend|apps|src)/)|结论|$)",
        plan_body,
    )
    lines = ["## 删除清单"]
    seen: set[str] = set()
    for path, desc in paths:
        path = path.strip().strip("`")
        if not path or path in seen:
            continue
        seen.add(path)
        desc = re.sub(r"^[\s：:，,。.-]+", "", (desc or "").strip())
        desc = re.sub(r"[\s。]+$", "", desc)
        lines.append(f"- `{path}`" + (f"：{desc}" if desc else ""))
    out = head
    if lines:
        out = (out + "\n\n" + "\n".join(lines)).strip() if out else "\n".join(lines)
    if rest.strip():
        out = (out + "\n\n" + rest.strip()).strip()
    return out


def _split_dialog_sentences(text: str) -> list[str]:
    """按中文句号切句，并尽量拆开粘连的清单行。"""
    t = _expand_glued_delete_plan(text or "")
    t = re.sub(r"(#{1,3})\s*(删除清单)", r"\n\n## 删除清单", t)
    t = re.sub(r"(?<!\n)(##\s*删除清单)", r"\n\n\1", t)
    t = re.sub(r"([。！？])\s*(#{1,3}\s*删除清单)", r"\1\n\n\2", t)
    t = re.sub(r"(结论[：:])\s*", r"\n\n\1", t)
    t = re.sub(r"([。！？])([^\n\s」』】）)])", r"\1\n\2", t)
    parts: list[str] = []
    for block in re.split(r"\n+", t):
        b = block.strip()
        if not b:
            continue
        if b.startswith("#") or b.startswith("- ") or b.startswith("* "):
            parts.append(b)
            continue
        buf = ""
        for ch in b:
            buf += ch
            if ch in "。！？":
                s = buf.strip()
                if s:
                    parts.append(s)
                buf = ""
        tail = buf.strip()
        if tail:
            parts.append(tail)
    return parts


def _prefer_dialog_sentence(a: str, b: str) -> str:
    """同义句保留排版更好的一版（空格、反引号更多者优先）。"""

    def score(s: str) -> tuple[int, int, int, int]:
        return (s.count(" "), s.count("`"), 1 if " → " in s else 0, len(s))

    return a if score(a) >= score(b) else b


def dedupe_dialog_sentences(text: str) -> str:
    """去掉近重复句，保留可读排版。"""
    parts = _split_dialog_sentences(text)
    out: list[str] = []
    keys: list[str] = []
    for part in parts:
        key = _norm_dialog_key(part)
        if not key:
            continue
        hit = -1
        for i, old_key in enumerate(keys):
            if _near_dup_keys(key, old_key):
                hit = i
                break
        if hit >= 0:
            out[hit] = _prefer_dialog_sentence(out[hit], part)
            keys[hit] = _norm_dialog_key(out[hit])
            continue
        out.append(part)
        keys.append(key)
    return "\n".join(out).strip()


def format_cursor_dialog(text: str) -> tuple[str, str]:
    """把 Cursor 对话框正文整理成：过程（优雅分段）+ 结论（短）。"""
    raw = dedupe_dialog_sentences(_collapse_repeated(text or ""))
    if not raw.strip():
        return "", ""
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    process_bits: list[str] = []
    plan_bits: list[str] = []
    conclusion = ""
    mode = "process"
    for ln in lines:
        if re.match(r"^#{0,3}\s*删除清单\b", ln) or ln == "删除清单":
            mode = "plan"
            if not plan_bits or plan_bits[0] != "## 删除清单":
                plan_bits = ["## 删除清单"] + [x for x in plan_bits if x != "## 删除清单"]
            continue
        if re.match(r"^结论[：:]", ln):
            conclusion = re.sub(r"^结论[：:]\s*", "", ln).strip() or conclusion
            mode = "process"
            continue
        if mode == "plan":
            m = re.match(r"^[-*]\s*`?([^`：:]+)`?\s*[：:]?\s*(.*)$", ln)
            if m and re.search(r"(frontend|backend|apps|src)/", m.group(1)):
                path = m.group(1).strip().strip("`")
                desc = (m.group(2) or "").strip()
                plan_bits.append(f"- `{path}`" + (f"：{desc}" if desc else ""))
            elif re.search(r"(frontend|backend|apps|src)/[\w./@-]+", ln):
                path_m = re.search(r"((?:frontend|backend|apps|src)/[\w./@-]+\.[A-Za-z0-9]+)", ln)
                if path_m:
                    rest = ln.replace(path_m.group(1), "").strip(" ：:-`")
                    plan_bits.append(f"- `{path_m.group(1)}`" + (f"：{rest}" if rest else ""))
                else:
                    plan_bits.append(ln)
            else:
                if "下线" in ln or "只需" in ln or ln.startswith("结论"):
                    conclusion = re.sub(r"^结论[：:]\s*", "", ln).strip()
                elif ln not in process_bits:
                    process_bits.append(ln)
            continue
        process_bits.append(ln)
    # 清单保序去重
    if plan_bits:
        uniq_plan: list[str] = []
        seen_p: set[str] = set()
        for x in plan_bits:
            k = _norm_dialog_key(x)
            if k in seen_p:
                continue
            seen_p.add(k)
            uniq_plan.append(x)
        plan_bits = uniq_plan
    process = "\n\n".join(process_bits).strip()
    if plan_bits:
        plan = "\n".join(plan_bits)
        process = (process + "\n\n" + plan).strip() if process else plan
    if not conclusion:
        for ln in reversed(process_bits):
            if "下线" in ln or ln.startswith("结论"):
                conclusion = re.sub(r"^结论[：:]\s*", "", ln).strip()
                break
    if conclusion:
        process = "\n\n".join(
            p for p in process.split("\n\n") if p.strip() and _norm_dialog_key(p) != _norm_dialog_key(conclusion)
        ).strip()
    delivery = f"**结论**\n{conclusion}" if conclusion else ""
    return process, delivery


def _absorb_plain(prev: str, incoming: str) -> str:
    """合并不含终稿标记的过程正文。"""
    p = prev or ""
    n = incoming or ""
    if not n:
        return p
    if not p:
        return n
    if n == p:
        return p
    if n.startswith(p):
        return n
    if p.startswith(n) and len(n) >= 24:
        return p
    if p.endswith(n):
        return p
    collapsed_n = _collapse_repeated(n)
    if collapsed_n != n:
        n = collapsed_n
        if n == p or n.startswith(p):
            return n if n.startswith(p) else p
    if len(n) > 24 and n in p:
        return _collapse_repeated(p)
    if len(p) > 24 and p in n:
        rest = n.replace(p, "", 1).strip()
        if not rest or rest == p.strip():
            return p
        return _collapse_repeated(n)
    if p.count("```") % 2 == 1 or n.lstrip().startswith("```") or len(n) < 48:
        return _collapse_phrase_dups(_glue_text_chunks(p, n))
    if "\n\n" not in n and not n.lstrip().startswith(("#", "|")):
        return _collapse_phrase_dups(_glue_text_chunks(p, n))
    return _collapse_repeated((p.rstrip() + "\n\n" + n.lstrip()).strip())


def _delivery_starts(text: str) -> list[int]:
    """终稿起点：说明方案 / 一句话结论 / **结论** 等。"""
    t = text or ""
    starts: list[int] = []
    for m in re.finditer(r"一句话结论", t):
        starts.append(m.start())
    for m in re.finditer(r"(^|\n|[。．])([ \t]*#{0,3}[ \t]*)说明方案", t, re.M):
        starts.append(m.start() + len(m.group(1) or "") + len(m.group(2) or ""))
    for m in re.finditer(r"(^|\n)\s*#{1,3}\s*说明方案", t, re.M):
        starts.append(m.start() + len(m.group(1) or ""))
    for m in re.finditer(r"(^|\n)\s*\*\*结论\*\*", t, re.M):
        starts.append(m.start() + len(m.group(1) or ""))
    return sorted(set(starts))


_PARTIAL_DELIVERY_HEAD = re.compile(
    r"^(说明方(?:案)?|一句话结论?|(\*\*)?结论(\*\*)?)",
    re.M,
)


def _split_process_delivery(body: str) -> tuple[str, str]:
    """拆分过程/终稿；流式未写完「说明方案」时也归入终稿通道，避免刷进正文。"""
    t = (body or "").strip()
    if not t:
        return "", ""
    starts = _delivery_starts(t)
    if starts:
        proc, delivery = split_delivery_markdown(t)
        return proc.strip(), delivery.strip()
    if _PARTIAL_DELIVERY_HEAD.match(t):
        return "", t
    return t, ""


_TOOL_ECHO_BARE = frozenset({"搜索", "查找文件", "列出", "写入", "阅读", "查看", "语义搜索"})
_TOOL_ECHO_PREFIX_RE = re.compile(
    r"^(阅读|查看|写入|列出|搜索|查找文件|语义搜索)\s+\S",
)


_TOOL_INLINE_RE = re.compile(
    r"(?:阅读|查看|搜索|查找文件|写入|列出|语义搜索)\s*"
    r"(?:`[^`]+`|"
    r"(?:frontend|backend|apps|src|desktop|host)/[\w./@-]+|"
    r"(?:frontend|backend|apps|src|desktop|host|DSH-ZR-WorkBuddy|"
    r"pythonProject[\w.-]*|agent-transcripts)\b|"
    r"[\w./@-]+\.[A-Za-z0-9]+)",
    re.I,
)


def _is_tool_echo_sentence(s: str) -> bool:
    """模型把工具名当正文刷出来的短句（查看 path / 搜索）。"""
    t = (s or "").strip()
    if t in _TOOL_ECHO_BARE:
        return True
    if not _TOOL_ECHO_PREFIX_RE.match(t):
        return False
    if "/" in t or "\\" in t or re.search(r"\.\w{1,10}\b", t):
        return True
    rest = _TOOL_ECHO_PREFIX_RE.sub("", t, count=1).strip()
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", rest))


def _line_looks_like_code(line: str) -> bool:
    s = (line or "").strip()
    if not s or s.startswith("```"):
        return False
    if re.search(
        r"\b(const|let|var|function|import|export|return|class|async|await|from|def|pass|raise|yield)\b",
        s,
    ):
        return True
    if re.match(r"^(from\s+\S+|import\s+|class\s+|def\s+|async\s+def|@)", s):
        return True
    if re.search(r"[{}();=<>]", s) and len(re.findall(r"[\u4e00-\u9fff]", s)) < 4:
        return True
    return False


def _scrub_tool_echo_in_process(text: str) -> str:
    """过程段去掉工具回声，说明方案原样保留。代码围栏内不拆句。"""
    proc, delivery = split_delivery_markdown(text or "")
    lines: list[str] = []
    in_fence = False
    for line in proc.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            lines.append(line)
            continue
        if in_fence:
            lines.append(line)
            continue
        if _line_looks_like_code(line):
            lines.append(line)
            continue
        line = _TOOL_INLINE_RE.sub("", line)
        keep: list[str] = []
        for bit in re.split(r"[。．]", line):
            s = bit.strip()
            if not s or _is_tool_echo_sentence(s):
                continue
            keep.append(s)
        if keep:
            joined = "。".join(keep)
            if not joined.endswith(("。", "！", "？", "；")):
                joined += "。"
            lines.append(joined)
    proc2 = "\n".join(lines).strip()
    if delivery:
        return f"{proc2}\n\n{delivery}".strip() if proc2 else delivery
    return proc2


def _strip_line_backticks(line: str) -> str:
    s = (line or "").strip()
    if len(s) >= 2 and s.startswith("`") and s.endswith("`") and "`" not in s[1:-1]:
        return s[1:-1]
    return line or ""


def _detect_code_lang_from_lines(lines: list[str]) -> str:
    norm = [str(_strip_line_backticks(ln)).strip() for ln in lines if str(ln or "").strip()]
    if not norm:
        return ""
    joined = "\n".join(norm)
    if re.search(r"<script[\s>]", joined, re.I):
        return "vue"
    if re.search(r"^<(template|script|style)\b", joined, re.I):
        return "vue"
    if re.search(r"^[\s<].*>", joined) and re.search(r"<\/?[\w-]+", joined):
        return "vue"
    if re.search(r"^(\s*(import|export|const|let|function|class|async)\b)", joined, re.M):
        return "javascript"
    if re.search(r"^(\s*(from\s+\w+\s+import|def\s+|class\s+|@router))", joined, re.M):
        return "python"
    return ""


def _repair_smashed_code(text: str) -> str:
    """把流式拼接粘在一起的关键字拆回合法代码行。"""
    s = text or ""
    s = re.sub(r"(import)([A-Za-z_])", r"\1 \2", s)
    s = re.sub(r"(from)(['\"])", r"\1 \2", s)
    s = re.sub(
        r"([A-Za-z0-9_\"'`)\]])(from|import|class|def|const|let|var|function|export|async|return|if|for|while|try|except|with)\b",
        r"\1\n\2",
        s,
    )
    s = re.sub(r"([\"'])([A-Za-z_]\w*)(from|import|const|let|function)\b", r"\1\n\2\3", s)
    s = re.sub(r"(\"{3}|'{3})([A-Za-z_])", r"\1\n\2", s)
    s = re.sub(r"(#[^\n]*?)([A-Za-z_]\w*\s*[:=])", r"\1\n\2", s)
    s = re.sub(r"(\})(const|let|var|function|import|export|class)\b", r"\1\n\2", s)
    return s


def _wrap_bare_code_runs_inner(text: str) -> str:
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        nonlocal run
        if not run:
            return
        body = "\n".join(str(_strip_line_backticks(ln)) for ln in run).strip()
        run = []
        if not body:
            return
        lang = _detect_code_lang_from_lines(body.split("\n")) or "text"
        if lang == "text" and not _line_looks_like_code(body.split("\n")[0]):
            out.append(body)
            return
        out.append(f"```{lang}\n{_repair_smashed_code(body)}\n```")

    for line in lines:
        raw = line or ""
        inner = _strip_line_backticks(raw)
        if raw.strip().startswith("```"):
            flush()
            out.append(line)
            continue
        wrapped = bool(re.fullmatch(r"`[^`]+`", raw.strip()))
        if _line_looks_like_code(inner) or wrapped or (run and not raw.strip()):
            run.append(inner if wrapped else raw)
            continue
        flush()
        out.append(line)
    flush()
    return "\n".join(out)


def _rewrite_fence_chunk(piece: str) -> str:
    """修复围栏内代码；未闭合围栏保持打开，便于流式展示。"""
    piece = (piece or "").strip()
    if not piece.startswith("```"):
        return ""
    open_fence = piece.count("```") == 1
    nl = piece.find("\n")
    if nl < 0:
        return piece if open_fence else ""
    head, body = piece[:nl], piece[nl + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
        open_fence = False
    body = _repair_smashed_code(body.strip("\n"))
    if not body.strip():
        return head if open_fence else ""
    if open_fence:
        return f"{head}\n{body}"
    return f"{head}\n{body}\n```"


def _ensure_code_fences(text: str) -> str:
    """裸代码包进 ``` 围栏；已有围栏内修复；未闭合围栏保持打开。"""
    t = (text or "").replace("\r\n", "\n")
    if not t.strip():
        return ""
    if "```" not in t:
        return _wrap_bare_code_runs_inner(t)
    bits: list[str] = []
    for kind, chunk in _segment_fences(t):
        piece = (chunk or "").strip()
        if not piece:
            continue
        if kind == "fence":
            rewritten = _rewrite_fence_chunk(piece)
            if rewritten.strip():
                bits.append(rewritten)
        else:
            wrapped = _wrap_bare_code_runs_inner(chunk)
            if wrapped.strip():
                bits.append(wrapped)
    return "\n\n".join(bits).strip()


def _line_looks_prose(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if re.search(r"[\u4e00-\u9fff]", s) and not re.search(
        r"[{}();=<>]|^\s*(import|from|def|class|const|let|function|async)\b",
        s,
    ):
        return True
    return False


def _strip_bare_code_from_process(text: str) -> str:
    """去掉围栏外的裸代码行；围栏本身由调用方决定保留或丢弃。"""
    t = (text or "").replace("\r\n", "\n")
    if not t.strip():
        return ""
    if "```" in t:
        bits: list[str] = []
        for kind, chunk in _segment_fences(t):
            if kind == "fence":
                bits.append(chunk.strip())
            else:
                prose = _strip_bare_code_from_process(chunk)
                if prose.strip():
                    bits.append(prose.strip())
        return "\n\n".join(bits).strip()
    kept: list[str] = []
    for line in t.split("\n"):
        raw = line or ""
        if raw.strip().startswith("```"):
            continue
        inner = _strip_line_backticks(raw).strip()
        if _line_looks_like_code(inner) and not _line_looks_prose(inner):
            continue
        if inner:
            kept.append(raw)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _strip_all_code_from_body(text: str) -> str:
    """正文/说明：去掉全部 ``` 代码块与裸代码，只保留中文说明。"""
    t = (text or "").replace("\r\n", "\n")
    if not t.strip():
        return ""
    if "```" in t:
        bits: list[str] = []
        for kind, chunk in _segment_fences(t):
            if kind == "fence":
                continue
            prose = _strip_all_code_from_body(chunk)
            if prose.strip():
                bits.append(prose.strip())
        return "\n\n".join(bits).strip()
    return _strip_bare_code_from_process(t)


def _finalize_process_body(text: str, *, keep_plan: bool = False) -> str:
    """过程正文落盘/展示。

    keep_plan=True（删除只读定位）：保留 Markdown 清单与路径行，只去掉大段源码围栏。
    默认：去掉全部代码块（写码任务正文禁贴源码）。
    """
    if keep_plan:
        return _keep_delete_plan_body(text or "")
    return _strip_all_code_from_body(text or "")


def _keep_delete_plan_body(text: str) -> str:
    """删除定位对话框正文：保留清单，去掉明显源码围栏。"""
    t = (text or "").replace("\r\n", "\n")
    if not t.strip():
        return ""
    if "```" not in t:
        return t.strip()
    bits: list[str] = []
    for kind, chunk in _segment_fences(t):
        if kind == "fence":
            # 短路径列表围栏可留；大段源码丢掉
            inner = re.sub(r"^```\w*\n?", "", chunk)
            inner = re.sub(r"\n?```$", "", inner)
            lines = [ln for ln in inner.splitlines() if ln.strip()]
            if len(lines) <= 24 and all(
                re.search(r"(frontend/|backend/|apps/|\.vue|\.js|\.ts|\.py|删除|清单)", ln)
                or len(ln) < 120
                for ln in lines[:12]
            ):
                bits.append(chunk.strip())
            continue
        if chunk.strip():
            bits.append(chunk.strip())
    return "\n\n".join(bits).strip()


def split_delivery_markdown(text: str) -> tuple[str, str]:
    """过程 = 第一处终稿标记之前；说明方案 = 优先从「说明方案/一句话结论」最后一次起。"""
    t = (text or "").replace("\r\n", "\n").strip()
    if not t:
        return "", ""
    starts = _delivery_starts(t)
    if not starts:
        return t, ""
    first = starts[0]

    def _is_scheme_start(i: int) -> bool:
        tail = t[i:].lstrip()
        return tail.startswith("说明方案") or tail.startswith("一句话结论") or tail.startswith("#")

    scheme = [i for i in starts if _is_scheme_start(i)]
    last = scheme[-1] if scheme else starts[-1]
    process = t[:first].rstrip(" \t。.;；、，").strip()
    delivery = t[last:].strip()
    return process, delivery


_PROCESS_HINT_RE = re.compile(
    r"(frontend/|backend/|apps/|src/|\.vue|\.js|\.py|AppLayout|router/|quality-|"
    r"已删除|改为|重定向|Index\.vue|permissions|/api/|"
    r"删除清单|待删|将删除|已定位到|准备删除|修补菜单|本机验尸)",
    re.I,
)

_EXPLORATION_MARKERS = (
    "正在定位",
    "正在搜索",
    "正在排查",
    "正在检查",
    "正在分析",
    "正在探索",
    "正在确认",
    "正在扩大",
    "正在回溯",
    "正在读取",
    "正在核对",
    "先定位",
    "开始分析",
    "开始探索",
    "开始处理",
    "接下来",
    "准备检查",
    "准备读取",
    "准备对比",
    "准备列出",
    "扩大搜索",
    "沙箱内",
    "沙箱中",
    "沙箱为",
    "沙箱仅",
    "沙箱缺少",
    "未发现",
    "进一步",
    "重新确认",
    "对照工作区",
    "处理改码",
    "探索代码库",
    "怀疑",
    "发现",
    "检查发现",
    "初步判断",
    "注意到",
    "推测",
    "正在权衡",
    "决定查看",
    "宿主机",
    "git ",
    "git历史",
    "历史记录",
    "对比确认",
    "回溯发现",
    "已理解需求",
    "将按 A",
    "无需额外",
    "当前工作树",
    "也在考虑",
)


def _segment_fences(text: str) -> list[tuple[str, str]]:
    """按顺序拆 prose / code fence（含未闭合围栏，便于流式展示代码）。"""
    parts: list[tuple[str, str]] = []
    i = 0
    t = text or ""
    while i < len(t):
        idx = t.find("```", i)
        if idx < 0:
            tail = t[i:].strip()
            if tail:
                parts.append(("prose", tail))
            break
        if idx > i:
            prose = t[i:idx].strip()
            if prose:
                parts.append(("prose", prose))
        end = t.find("```", idx + 3)
        if end < 0:
            parts.append(("fence", t[idx:].strip()))
            break
        parts.append(("fence", t[idx : end + 3].strip()))
        i = end + 3
    return parts


def _is_exploration_prose(text: str) -> bool:
    """读盘/搜代码自言自语 → 思考区；含路径或改动/删除说明的短句 → 正文过程。"""
    t = (text or "").strip()
    if not t or _delivery_starts(t):
        return False
    if _PROCESS_HINT_RE.search(t):
        return False
    # 明确的删除执行进度必须进正文流式；纯「正在分析/探索」仍进思考
    if re.search(
        r"(删除清单|待删|将删除|已删除|已定位到|准备删除|修补菜单|本机验尸|阶段\s*\d+\s*/\s*\d+)",
        t,
    ):
        return False
    if re.search(
        r"(菜单|路由|页面).{0,16}(删除|下线|移除|排产)|(删除|下线|移除).{0,16}(菜单|路由|页面|排产|子项)",
        t,
    ):
        return False
    if len(t) <= 56 and not any(m in t for m in _EXPLORATION_MARKERS):
        return False
    if len(t) > 72:
        return True
    return any(m in t for m in _EXPLORATION_MARKERS)


def split_assistant_channels(body: str) -> tuple[str, str, str]:
    """返回 (探索→思考, 过程正文 B, 终稿 C)。"""
    t = (body or "").strip()
    if not t:
        return "", "", ""
    proc_part, delivery = _split_process_delivery(t)
    explore_bits: list[str] = []
    process_bits: list[str] = []
    for kind, chunk in _segment_fences(proc_part):
        if kind == "fence":
            process_bits.append(chunk)
            continue
        paragraphs = re.split(r"\n\s*\n", chunk)
        if len(paragraphs) <= 1 and chunk.count("\n") >= 1:
            paragraphs = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        for para in paragraphs:
            piece = str(para or "").strip()
            if not piece:
                continue
            if _line_looks_like_code(piece.split("\n")[0]) and not _line_looks_prose(piece):
                # 裸代码进过程通道，由 _finalize_process_body 包进围栏流式展示
                process_bits.append(piece)
                continue
            if _is_exploration_prose(piece):
                explore_bits.append(piece)
            else:
                process_bits.append(piece)
    return (
        "\n\n".join(explore_bits).strip(),
        "\n\n".join(process_bits).strip(),
        delivery.strip(),
    )


def split_public_live_body(body: str) -> tuple[str, str]:
    """兼容旧调用：探索, 过程+终稿。"""
    explore, process, delivery = split_assistant_channels(body)
    public = process
    if delivery:
        public = (public + "\n\n" + delivery).strip() if public else delivery
    return explore, public


def _has_balanced_fences(text: str) -> bool:
    return text.count("```") >= 2 and text.count("```") % 2 == 0


def _gate_stream_process(body: str, process: str) -> str:
    """流式过程正文：只保留说明文字，全部代码块/裸代码不进正文。"""
    del body
    return _finalize_process_body(process or "")


def streamable_public_body(body: str) -> str:
    """过程正文：改动说明（不含探索、不含终稿、不含代码）。"""
    _, process, _ = split_assistant_channels(body)
    return _gate_stream_process(body, process)


def sanitize_public_live_text(body: str, *, seed: str = "", activity: str = "") -> str:
    """live_text 落盘：仅过程正文 B（无代码）。"""
    process = streamable_public_body(body)
    parts: list[str] = []
    if process:
        parts.append(process)
    elif seed:
        parts.append(seed)
    elif activity:
        parts.append(activity)
    text = "\n\n".join(p for p in parts if p and str(p).strip())
    text = _collapse_repeated(_fix_broken_cjk_punct(text))
    return text


def _sanitize_delivery_body(delivery: str) -> str:
    """说明方案：去掉代码片段，只保留结构化说明。"""
    t = (delivery or "").strip()
    if not t:
        return ""
    t = _scrub_tool_echo_in_process(t)
    t = _strip_all_code_from_body(t)
    return _collapse_repeated(_fix_broken_cjk_punct(t))


def sanitize_delivery_text(body: str) -> str:
    _, _, delivery = split_assistant_channels(body)
    if not delivery:
        return ""
    return _sanitize_delivery_body(delivery)


def _absorb_text(prev: str, incoming: str) -> str:
    """合并增量或全量快照。终稿只保留最后一份，过程与说明方案不叠写。"""
    p = prev or ""
    n = incoming or ""
    if not n:
        return p
    if not p:
        return n
    if n == p:
        return p
    p_starts = _delivery_starts(p)
    n_starts = _delivery_starts(n)
    if p_starts or n_starts:
        p_proc, p_del = split_delivery_markdown(p)
        n_proc, n_del = split_delivery_markdown(n)
        if not n_starts:
            if p_del:
                merged = _absorb_plain(p_del, n)
                return (p_proc.rstrip() + "\n\n" + merged).strip() if p_proc else merged
            return _absorb_plain(p, n)
        proc = _absorb_plain(p_proc, n_proc) if n_proc else p_proc
        delivery = n_del or p_del
        if proc and delivery:
            return (proc.rstrip() + "\n\n" + delivery.lstrip()).strip()
        return (delivery or proc).strip()
    return _absorb_plain(p, n)


def extract_delivery_markdown(text: str) -> str:
    """终稿优先；没有「一句话结论」时退回全文。"""
    process, delivery = split_delivery_markdown(text)
    return delivery or process


def _merge_assistant_delta(prev: str, piece: str) -> tuple[str, str, bool]:
    """返回 (full, delta, replaced)。"""
    p = prev or ""
    n = piece or ""
    if not n:
        return p, "", False
    full = _absorb_text(p, n)
    if full == p:
        return p, "", False
    if full.startswith(p):
        return full, full[len(p) :], False
    return full, full, True


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        for name in names:
            if obj.get(name) not in (None, ""):
                return obj.get(name)
        return default
    for name in names:
        val = getattr(obj, name, None)
        if val not in (None, ""):
            return val
    return default


def _is_read_tool_name(name: str) -> bool:
    n = (name or "").strip().lower()
    return n in {
        "read",
        "glob",
        "grep",
        "semanticsearch",
        "list",
        "list_dir",
        "search",
        "find",
        "ripgrep",
    }


def _is_write_tool_name(name: str) -> bool:
    n = (name or "").strip().lower()
    return n in {"write", "edit", "strreplace", "delete", "apply_patch", "create", "patch"}


class _CursorStreamSink:
    """把 SDK 增量/步骤折叠成面板能显示的思考过程。"""

    def __init__(
        self,
        sink: Sink | None,
        sandbox: str = "",
        *,
        max_read_tools: int = 28,
        read_only: bool = False,
        on_read_budget: Callable[[], None] | None = None,
        on_write_violation: Callable[[], None] | None = None,
    ):
        self.sink = sink
        self.sandbox = sandbox
        self.max_read_tools = max(8, int(max_read_tools or 28))
        self.read_only = bool(read_only)
        self._on_read_budget = on_read_budget
        self._on_write_violation = on_write_violation
        self._read_tool_count = 0
        self._write_tool_seen = False
        self._write_violation_fired = False
        self._budget_fired = False
        self.final_text = ""
        self._seed_line = ""
        self._assistant_body = ""
        self._process_body = ""
        self._delivery_body = ""
        self._last_delivery = ""
        self.reasoning = ""
        self.activity: list[str] = []
        self.think_ms: int | None = None
        self.placeholder = True
        self.failure_detail = ""
        self._tool_keys: set[str] = set()
        self._got_text_delta = False
        self._got_think_delta = False
        self._activity_by_path: dict[str, str] = {}
        self._activity_order: list[str] = []

    def _rebuild_live_text(self) -> None:
        """写码：过程说明；删除只读：尽量贴近 Cursor 对话框（助手文 + 思考文 + 工具行）。"""
        if self.read_only:
            raw = (self._assistant_body or "").strip()
            body = ""
            if raw:
                proc_only, _del = _split_process_delivery(raw)
                body = _finalize_process_body(proc_only or raw, keep_plan=True)
            if is_engine_seed_text(body):
                body = ""
            # 删除任务常见：模型只往思考区写 → 把思考同步进正文（对话框观感）
            # 注意：一旦已有助手可见文（含流式短前缀），不要再把思考拼进正文，避免「半句助手+整段思考」糊在一起
            think = (self.reasoning or "").strip() if (self._got_think_delta and not self.placeholder) else ""
            if think and not body and not self._got_text_delta:
                body = think
            # 仍无助手/思考时，把工具活动行拼进正文（贴近 Cursor 对话里的工具卡片）
            if (not body or is_engine_seed_text(body)) and self.activity:
                act = "\n".join(str(x).strip() for x in self.activity[-24:] if str(x).strip())
                if act:
                    body = act
            # 仅启动瞬间用种子句占位；有真实内容后不再回退到种子
            if not body and self._seed_line:
                body = self._seed_line
            body = _scrub_public_text(body, self.sandbox)
            body = _collapse_repeated(_fix_broken_cjk_punct(body))
            if body and not is_engine_seed_text(body):
                # 流式阶段只做近重复去重，完整排版留给 export/收尾
                body = dedupe_dialog_sentences(body)
            if body == self.final_text:
                return
            self.final_text = body
            if body:
                _emit(self.sink, {"type": "replace_text", "text": self.final_text})
            return
        parts: list[str] = []
        process = self._process_body.strip()
        if process:
            proc_only, _stray_del = _split_process_delivery(process)
            process = proc_only.strip()
        if process:
            parts.append(process)
        # 正文仍空时，用工具进展/种子句撑住流式，避免长时间空白
        if not process:
            if self._seed_line:
                parts.append(self._seed_line)
            for line in self.activity[-6:]:
                s = str(line or "").strip()
                if not s:
                    continue
                # 工具行改成中性说明，避免被 tool-echo 清扫掉
                if re.match(r"^(阅读|查看|搜索|查找文件|列出|写入)\s+", s):
                    s = "正在对照工作区定位相关文件。"
                if s and s not in parts:
                    parts.append(s)
        text = "\n\n".join(p for p in parts if p and str(p).strip())
        text = _scrub_public_text(text, self.sandbox)
        text = _collapse_repeated(_fix_broken_cjk_punct(text))
        # 仅当整段是终稿头时才清空；过程中夹带「结论」二字不整段抹掉
        if text and (_PARTIAL_DELIVERY_HEAD.match(text.strip()) and not process):
            text = ""
        if text == self.final_text:
            return
        self.final_text = text
        _emit(self.sink, {"type": "replace_text", "text": self.final_text})

    def _emit_delivery_if_changed(self) -> None:
        delivery = (self._delivery_body or "").strip()
        if not delivery:
            _, delivery = _split_process_delivery(self._assistant_body.strip())
        if not delivery:
            delivery = sanitize_delivery_text(self._assistant_body)
        delivery = _sanitize_delivery_body(delivery.strip())
        self._delivery_body = delivery
        if delivery == self._last_delivery:
            return
        self._last_delivery = delivery
        if delivery:
            _emit(self.sink, {"type": "replace_delivery", "text": delivery})

    def composed_public_reply(self) -> str:
        """任务收尾/校验用：过程正文 + 终稿（不含探索）。"""
        parts: list[str] = []
        if self._process_body.strip():
            parts.append(self._process_body.strip())
        delivery = self._last_delivery or sanitize_delivery_text(self._assistant_body)
        if delivery:
            parts.append(delivery)
        if parts:
            return "\n\n".join(parts)
        return self.final_text.strip()

    def export_dialog(self) -> dict[str, str]:
        """导出接近 Cursor 对话框的正文/终稿，供面板展示。"""
        raw = (self._assistant_body or "").strip()
        proc, delivery = _split_process_delivery(raw) if raw else ("", "")
        if not proc:
            proc = (self.final_text or self._process_body or "").strip()
        if is_engine_seed_text(proc):
            proc = ""
        think = (self.reasoning or "").strip()
        if self.placeholder:
            think = ""
        # 删除定位：无助手可见文时，用思考区或工具行充当对话框正文
        if self.read_only:
            if think and not proc:
                proc = think
            if (not proc or is_engine_seed_text(proc)) and self.activity:
                act = "\n".join(str(x).strip() for x in self.activity[-24:] if str(x).strip())
                if act:
                    proc = act
        if not delivery:
            delivery = (self._last_delivery or "").strip()
        # 终稿也禁止回落引擎种子句
        final = (self.final_text or proc or "").strip()
        if is_engine_seed_text(final):
            final = proc
        # 去重 + 优雅分段（删除定位对话框）
        if self.read_only and (proc or delivery or final):
            pretty_proc, pretty_del = format_cursor_dialog(proc or final)
            if pretty_proc:
                proc = pretty_proc
                final = pretty_proc
            if pretty_del and (not delivery or is_engine_seed_text(delivery) or len(delivery) > len(pretty_del) * 2):
                delivery = pretty_del
        return {
            "assistant_raw": raw or proc,
            "process": proc,
            "delivery": delivery,
            "final_text": final,
            "thinking": think,
        }

    def seed_process(self, sentence: str) -> None:
        """任务一开始就往正文塞一句，避免思考空转时正文空白。"""
        s = str(sentence or "").strip()
        if not s or self._assistant_body.strip():
            return
        if not s.endswith("。"):
            s += "。"
        self._seed_line = s
        self._rebuild_live_text()

    def composed_think(self) -> str:
        if self.reasoning.strip():
            return self.reasoning.strip()
        if self.placeholder:
            return "先对齐需求，摸清现有模块和接口，再按最小改动落地。"
        return ""

    def flush_think(self, *, duration: int | None = None, finish: bool = False) -> None:
        if finish and duration is not None:
            try:
                self.think_ms = max(0, int(duration))
            except (TypeError, ValueError):
                pass
        payload: dict[str, Any] = {
            "type": "thinking",
            "text": self.composed_think(),
            "snapshot": True,
        }
        # 任务未结束时不发 duration，避免进度卡过早收成「已完成思考」
        if finish and self.think_ms is not None:
            payload["thinking_duration_ms"] = self.think_ms
        _emit(self.sink, payload)

    def add_reasoning_delta(self, piece: str) -> None:
        n = str(piece or "")
        if not n:
            return
        if self.placeholder:
            self.reasoning = ""
            self.placeholder = False
        self._got_think_delta = True
        self.reasoning = _absorb_text(self.reasoning, n)
        if len(self.reasoning) > 12000:
            self.reasoning = self.reasoning[-12000:]
        self.flush_think()
        if not self._got_text_delta:
            self._rebuild_live_text()

    def set_reasoning_full(self, piece: str, dur: int | None = None) -> None:
        n = str(piece or "")
        if n:
            if self.placeholder:
                self.placeholder = False
            self.reasoning = _absorb_text(self.reasoning, n)
        self.flush_think()
        if not self._got_text_delta:
            self._rebuild_live_text()

    def _append_reasoning(self, piece: str) -> None:
        n = _collapse_repeated(_fix_broken_cjk_punct(str(piece or "").strip()))
        if not n:
            return
        if self.placeholder:
            self.reasoning = ""
            self.placeholder = False
        self.reasoning = _absorb_text(self.reasoning, n)
        if len(self.reasoning) > 12000:
            self.reasoning = self.reasoning[-12000:]
        self.flush_think()
        # 删除只读：思考同步进正文（许多回合只有 thinking、没有 assistant 可见文）
        if self.read_only:
            self._rebuild_live_text()

    def _sync_channels(self) -> None:
        """按 A/B/C 拆分：探索→思考；过程说明→正文；终稿→delivery。

        删除只读：不把助手文拆进「探索」，整段留在过程区（贴近对话框）。
        """
        if self.read_only:
            raw = (self._assistant_body or "").strip()
            proc, delivery = _split_process_delivery(raw)
            body = proc or raw
            self._process_body = _finalize_process_body(body, keep_plan=True)
            if delivery:
                self._delivery_body = _sanitize_delivery_body(delivery)
                self._emit_delivery_if_changed()
            self._rebuild_live_text()
            return
        explore, process, delivery = split_assistant_channels(self._assistant_body.strip())
        if explore:
            self._append_reasoning(explore)
        # 展示层：写码去代码；删除定位保留清单（贴近对话框）
        self._process_body = _finalize_process_body(process, keep_plan=self.read_only)
        raw_process = (process or "").strip()
        raw_delivery = (delivery or "").strip()
        if raw_delivery:
            self._delivery_body = _sanitize_delivery_body(raw_delivery)
        self._emit_delivery_if_changed()
        kept: list[str] = []
        if raw_process:
            kept.append(raw_process)
        if raw_delivery:
            kept.append(raw_delivery)
        self._assistant_body = "\n\n".join(kept).strip()

    def add_assistant_piece(self, piece: str, *, from_delta: bool = False) -> None:
        n = _scrub_public_text(str(piece or ""), self.sandbox)
        if not n:
            return
        if from_delta:
            self._got_text_delta = True
        prev_body = self._assistant_body
        self._assistant_body, _, _ = _merge_assistant_delta(self._assistant_body, n)
        self._assistant_body = _scrub_public_text(self._assistant_body, self.sandbox)
        if not self._assistant_body or self._assistant_body == prev_body:
            if from_delta and not self._assistant_body:
                self._rebuild_live_text()
            return
        self._sync_channels()
        if self._process_body.strip() or self._delivery_body.strip():
            self._seed_line = ""
        self._rebuild_live_text()

    def _note_tool_budget(self, name: str, *, new_key: bool) -> None:
        if _is_write_tool_name(name):
            self._write_tool_seen = True
            if self.read_only and not self._write_violation_fired and self._on_write_violation:
                self._write_violation_fired = True
                _emit(
                    self.sink,
                    {
                        "type": "status",
                        "text": "只读定位阶段禁止改文件；已中止 Cursor 写入并收束输出删除清单。",
                    },
                )
                try:
                    self._on_write_violation()
                except Exception:
                    pass
            return
        if not new_key or not _is_read_tool_name(name):
            return
        self._read_tool_count += 1
        if (
            not self._write_tool_seen
            and self._read_tool_count >= self.max_read_tools
            and not self._budget_fired
            and self._on_read_budget
        ):
            self._budget_fired = True
            _emit(
                self.sink,
                {
                    "type": "status",
                    "text": f"读盘已达上限（{self.max_read_tools} 次），正在要求 Cursor 收束并输出终稿…",
                },
            )
            try:
                self._on_read_budget()
            except Exception:
                pass

    def add_tool(self, *, name: str, status: str, args: Any = None, call_id: str = "") -> None:
        st = (status or "running").strip().lower()
        if st in {"started", "start"}:
            st = "running"
        line = _tool_activity_line(name=name, status=st, args=args, sandbox=self.sandbox)
        if not line:
            return
        # 完成事件只更新 tool_call 通道，不再追加一条「查看」
        if st == "completed":
            key = (call_id or line).strip()
            if key in self._tool_keys:
                return
            self._tool_keys.add(key)
            self._note_tool_budget(name, new_key=True)
            _emit(
                self.sink,
                {"type": "tool_call", "name": name, "status": st, "text": line, "call_id": call_id},
            )
            return
        key = (call_id or _activity_path_key(line) or line).strip()
        if key in self._tool_keys and st != "error":
            # 同一路径重复 running：刷新顺序，不重复刷屏
            _record_activity_line(self._activity_by_path, self._activity_order, line)
            self.activity = [self._activity_by_path[k] for k in self._activity_order][-12:]
            _emit(
                self.sink,
                {"type": "tool_call", "name": name, "status": st, "text": line, "call_id": call_id},
            )
            if (not self._got_text_delta) or (not self._process_body.strip()):
                self._rebuild_live_text()
            return
        if key:
            self._tool_keys.add(key)
        self._note_tool_budget(name, new_key=bool(key))
        _record_activity_line(self._activity_by_path, self._activity_order, line)
        self.activity = [self._activity_by_path[k] for k in self._activity_order][-12:]
        _emit(
            self.sink,
            {"type": "tool_call", "name": name, "status": st, "text": line, "call_id": call_id},
        )
        if (not self._got_text_delta) or (not self._process_body.strip()):
            self._rebuild_live_text()

    def handle_delta(self, update: Any) -> None:
        utype = str(_attr(update, "type", default="") or "")
        if utype == "thinking-delta":
            self.add_reasoning_delta(str(_attr(update, "text", default="") or ""))
        elif utype == "thinking-completed":
            self.flush_think()
        elif utype == "text-delta":
            self.add_assistant_piece(str(_attr(update, "text", default="") or ""), from_delta=True)
        elif utype in {"tool-call-started", "partial-tool-call"}:
            tool = _attr(update, "tool_call", "toolCall", default={}) or {}
            name, args = _tool_name_and_args(tool)
            self.add_tool(
                name=name,
                status="running",
                args=args if args else tool,
                call_id=str(_attr(update, "call_id", "callId", default="") or ""),
            )
        elif utype == "tool-call-completed":
            tool = _attr(update, "tool_call", "toolCall", default={}) or {}
            name, args = _tool_name_and_args(tool)
            self.add_tool(
                name=name,
                status="completed",
                args=args if args else tool,
                call_id=str(_attr(update, "call_id", "callId", default="") or ""),
            )

    def handle_step(self, step: Any) -> None:
        stype = str(_attr(step, "type", default="") or "")
        msg = _attr(step, "message", default=None)
        if stype == "thinkingMessage":
            text, dur = _thinking_from_message(msg if msg is not None else step)
            if not text:
                text, dur2 = _thinking_from_message(step)
                dur = dur if dur is not None else dur2
            self.set_reasoning_full(text, dur)
        elif stype in {"assistantMessage", "assistant_message", "assistant"}:
            text = ""
            if msg is not None:
                text = str(getattr(msg, "text", None) or "").strip()
                if not text and isinstance(msg, dict):
                    text = str(msg.get("text") or "").strip()
            if not text:
                text = _assistant_text_from_message(msg if msg is not None else step).strip()
            if text:
                self.add_assistant_piece(text)
        elif stype in {"toolCall", "tool_call"}:
            payload = msg if isinstance(msg, dict) else _as_mapping(msg) or _as_mapping(step)
            name, args = _tool_name_and_args(payload)
            self.add_tool(
                name=name,
                status=str(payload.get("status") or "running"),
                args=args if args else payload,
                call_id=str(payload.get("call_id") or payload.get("callId") or ""),
            )

    def handle_message(self, message: Any) -> None:
        mtype, st_status, st_msg = _sdk_message_fields(message)
        if mtype == "status" and st_msg:
            if st_status.upper() in {"ERROR", "FAILED"} or _USAGE_LIMIT_RE.search(str(st_msg)):
                self.failure_detail = st_msg
        if mtype == "thinking":
            # stream 常推完整 thinking 快照；有 delta 时仍吸收更长快照
            piece, _dur_ms = _thinking_from_message(message)
            if piece:
                self.set_reasoning_full(piece)
            return
        elif mtype in {"tool_call", "toolCall"}:
            args = _attr(message, "args", "arguments", "params", default=None)
            name, parsed = _tool_name_and_args(args if isinstance(args, dict) else message)
            self.add_tool(
                name=str(_attr(message, "name", "tool", "toolName", default=name) or name),
                status=str(_attr(message, "status", default="running") or "running"),
                args=parsed or args or message,
                call_id=str(_attr(message, "call_id", "callId", default="") or ""),
            )
        elif mtype == "assistant":
            if self._got_text_delta:
                return
            self.add_assistant_piece(_assistant_text_from_message(message))
        elif mtype == "task":
            text = str(_attr(message, "text", default="") or "")
            if text:
                _emit(self.sink, {"type": "status", "text": _short_text(text, 160), "phase": "agent"})


def _safe_cb(fn: Callable[[Any], None], sink: Sink | None) -> Callable[[Any], None]:
    def _wrap(value: Any) -> None:
        try:
            fn(value)
        except Exception as exc:  # noqa: BLE001
            _emit(sink, {"type": "status", "text": f"进度回调异常：{type(exc).__name__}: {exc}"[:240]})

    return _wrap


def _dialog_captured(bus: _CursorStreamSink) -> bool:
    """是否已有可展示的 Cursor 正文（助手文或真实思考，不含占位）。"""
    if str(bus._assistant_body or "").strip():
        return True
    if bus.reasoning.strip() and not bus.placeholder:
        think = bus.reasoning.strip()
        if think and think != "先对齐需求，摸清现有模块和接口，再按最小改动落地。":
            return True
    return False


def _ingest_conversation(bus: _CursorStreamSink, run_obj: Any, *, force: bool = False) -> None:
    """流结束后补捞会话步骤（thinking / assistant / tool）。"""
    if not force and _dialog_captured(bus) and bus.activity:
        return
    conv_fn = getattr(run_obj, "conversation", None)
    if not callable(conv_fn):
        return
    try:
        turns = conv_fn()
    except Exception:
        return
    for turn in turns or []:
        inner = getattr(turn, "turn", None)
        if inner is None and isinstance(turn, dict):
            inner = turn.get("turn")
        steps = getattr(inner, "steps", None) if inner is not None else None
        if steps is None and isinstance(inner, dict):
            steps = inner.get("steps")
        for step in steps or []:
            try:
                bus.handle_step(step)
            except Exception:
                continue


def _harvest_run_dialog(bus: _CursorStreamSink, run_obj: Any, result: Any = None) -> None:
    """多通道捞 Cursor 对话框：conversation → result.result → iter_text。"""
    _ingest_conversation(bus, run_obj, force=True)
    result_text = ""
    if result is not None:
        result_text = str(
            getattr(result, "result", None) or getattr(result, "text", None) or ""
        ).strip()
    if result_text:
        bus.add_assistant_piece(result_text)
    # 再扫一遍 messages/stream 缓冲（部分 SDK 版本 conversation 空、messages 有）
    for attr in ("messages", "stream"):
        if _dialog_captured(bus) and bus._assistant_body.strip():
            break
        fn = getattr(run_obj, attr, None)
        if not callable(fn):
            continue
        try:
            for event in fn():
                try:
                    msg = getattr(event, "sdk_message", None)
                    bus.handle_message(msg if msg is not None else event)
                except Exception:
                    continue
        except Exception:
            continue
    try:
        iter_text = getattr(run_obj, "iter_text", None)
        if callable(iter_text) and not str(bus._assistant_body or "").strip():
            chunks = []
            for piece in iter_text():
                s = str(piece or "")
                if s:
                    chunks.append(s)
            if chunks:
                bus.add_assistant_piece("".join(chunks))
    except Exception:
        pass
    bus._sync_channels()
    bus._rebuild_live_text()
    bus._emit_delivery_if_changed()


def build_delete_plan_prompt(*, requirement: str, workspace_hint: str) -> str:
    """删除类：仅读盘定位，禁止改文件；终稿只输出待删清单。"""
    req = (requirement or "").strip()
    return (
        "你正在 ZR-WorkBuddy 本机写码沙箱中做【删除定位】（只读阶段）。\n"
        f"【本机工程】{workspace_hint}\n\n"
        "【硬性禁令】\n"
        "- 禁止 Write/Edit/Delete/rm/ApplyPatch 等任何改文件操作；只允许 Read/Grep/List。\n"
        "- 禁止实现新的删除接口、删除按钮或 CRUD；目标是下线已有功能。\n"
        "- 读盘预算：最多 12 个不同文件；定位后立刻输出清单，禁止超过 2 分钟仍只读。\n\n"
        "【输出格式】正文必须边定位边流式写中文短句（每句一行），说明正在看菜单/路由/页面；"
        "禁止只把进展写进思考区。终稿第一行必须是：\n"
        "## 删除清单\n"
        "随后每行一个待删相对路径（须本机真实存在），格式：\n"
        "- `frontend/src/.../Xxx.vue`：页面组件\n"
        "- `frontend/src/api/xxx.js`：API 封装\n"
        "- `backend/app/routers/xxx.py` 中某段路由（若整文件仅服务该功能可列整文件）\n"
        "不要改 AppLayout.vue / router/index.js 的内容（引擎会自动修补菜单路由）。\n"
        "不要输出「说明方案」四段式，只输出过程短句 + 删除清单与 1～2 句结论。禁止贴代码块。\n\n"
        f"【需求】\n{req}\n"
    )


def build_prompt(*, requirement: str, workspace_hint: str, empty_target: bool) -> str:
    from .brief import is_delete_intent

    mode = (
        "空目录新项目：请从零生成可运行的最小实现"
        if empty_target
        else "已有工程（工作区即沙箱拷贝）：请在现有结构上增量修改"
    )
    req = (requirement or "").strip()
    delete_block = ""
    if is_delete_intent(req):
        delete_block = (
            "【删除/下线任务·硬性要求】\n"
            "目标是**从工程中移除/下线已有功能**，不是实现新的「删除按钮/删除接口/CRUD」。"
            "禁止新增 delete API、禁止写列表页删行逻辑、禁止扩功能。\n"
            "1. 须同时改菜单（AppLayout.vue）、路由（router/index.js），并物理删除页面/API 文件。\n"
            "2. 页面/组件须在沙箱内 rm/Delete；只在终稿写「已删除」无效。\n"
            "3. 读盘预算：最多 12 个文件；定位后立刻改，禁止超过 3 分钟只读。\n\n"
        )
    return (
        "你正在 ZR-WorkBuddy 的本机写码沙箱中执行改码任务。\n"
        "【工作区】当前 cwd 就是沙箱根目录，请直接读写此目录内文件。\n"
        f"【目标模式】{mode}\n"
        f"【用户确认的本机同步目录（勿当作 cwd；任务成功后由系统同步）】{workspace_hint}\n\n"
        "输出必须严格按 A→B→C，禁止打乱、禁止把终稿写两遍。\n"
        "A. 思考：只写在内部思考。短句推进（定位 → 现有结构 → 准备怎么改）。"
        "禁止反复刷同一句「正在xxx」；不要输出工具原始路径。\n"
        "B. 正文：边改边写，必须流式输出中文说明。每段最多两句，句号后换行，禁止一整段墙式文字。"
        "每改一个文件，用一两句说明改了什么、改了哪个路径；禁止贴代码块、禁止贴大段源码、禁止贴 script/style。"
        "正文只允许说明文字与文件路径，代码改动只写入工作区文件。"
        "此阶段禁止出现「一句话结论」「说明方案」「改动文件」「验收步骤」。\n"
        "C. 全部改完后另起一行，只写一份终稿，第一行必须恰好是：\n"
        "## 说明方案\n"
        "随后用正文，禁止表格、禁止 Tab 分列、禁止再重复一遍：\n"
        "**结论**\n"
        "一段话写清做了什么。\n"
        "**改动文件**\n"
        "- `path/to/file`：改了什么\n"
        "**行为约定**\n"
        "- 已删除：…\n"
        "- 保留：…\n"
        "- 未改动：…\n"
        "**验收**\n"
        "1. …\n"
        "2. …\n"
        "规则：只改本工作区（cwd）内文件；最小必要改动；删除的文件系统会同步从本机工程删掉。"
        "禁止读写宿主机家目录、`.ssh`、`.env`、密钥。\n\n"
        f"{delete_block}"
        f"【需求】\n{req}\n"
    )


def _format_cursor_agent_error(err: Any) -> str:
    """把 SDK 的 internal error 补上 code/cause，避免界面只剩三个英文单词。"""
    msg = str(getattr(err, "message", None) or err or "").strip() or "unknown"
    code = str(getattr(err, "code", None) or "").strip()
    status = getattr(err, "status", None)
    rid = str(getattr(err, "request_id", None) or "").strip()
    cause = getattr(err, "cause", None) or getattr(err, "__cause__", None)
    details = getattr(err, "details", None)
    bits = [msg]
    extra: list[str] = []
    if code and code.lower() not in msg.lower():
        extra.append(str(code))
    if status not in (None, ""):
        extra.append(f"HTTP {status}")
    if rid:
        extra.append(f"req {rid[:16]}")
    if extra:
        bits.append("(" + ", ".join(extra) + ")")
    if cause:
        cmsg = str(cause).strip()
        if cmsg and cmsg.lower() not in msg.lower():
            bits.append(f"原因：{cmsg[:180]}")
    if isinstance(details, list) and details:
        bits.append(str(details[0])[:160])
    out = " ".join(bits)
    if status == 429 or "usage limit" in msg.lower() or "out of usage" in msg.lower():
        out += "。这是额度或用量限制，请到 Cursor 设置里查看 Usage。"
    elif "internal error" in msg.lower() or status == 500:
        out += "。这是 Cursor 云端瞬时故障，不是额度用尽（额度用尽一般是 429）。请再点一次确认开工；若连续失败，等一两分钟再试。"
    return out[:480]



_ENGINE_SEED_LINES = {
    "正在只读定位待删文件，输出删除清单。",
    "正在只读定位待删文件。",
    "正在启动 Cursor，开始对照工作区定位相关代码。",
}


def is_engine_seed_text(text: str) -> bool:
    """引擎占位种子句，不能当成 Cursor 对话框正文。"""
    s = str(text or "").strip()
    if not s:
        return False
    if s in _ENGINE_SEED_LINES:
        return True
    bare = s.rstrip("。.;；")
    return any(bare == x.rstrip("。.;；") for x in _ENGINE_SEED_LINES)


def looks_like_delete_plan_reply(text: str) -> bool:
    """真正含删除清单/路径的 Cursor 回复；种子句不算。"""
    t = str(text or "").strip()
    if not t or is_engine_seed_text(t):
        return False
    if "`frontend/" in t or "frontend/src/" in t:
        return True
    if "## 删除清单" in t:
        return True
    if "删除清单" in t and ("`" in t or "- " in t or "* " in t):
        return True
    return False


def _with_dialog(bus: "_CursorStreamSink", payload: dict) -> dict:
    """给返回值附上对话框原文，供面板优先展示 Cursor 输出。"""
    try:
        dlg = bus.export_dialog()
    except Exception:
        dlg = {}
    out = dict(payload)
    out.update({k: v for k, v in dlg.items() if v})
    return out


def run_cursor_local_agent(
    *,
    sandbox: Path,
    prompt: str,
    sink: Sink | None,
    step: Callable[..., None],
    is_cancel_requested: Callable[[], bool],
    timeout_sec: int = 2700,
    max_read_tools: int = 28,
    read_only: bool = False,
) -> dict[str, Any]:
    """返回 {ok, text, agent_id, run_id, error}；额度用尽时自动切 Auto 再试。"""
    avail = config_availability()
    if not avail.get("ok"):
        return {
            "ok": False,
            "text": "",
            "agent_id": "",
            "run_id": "",
            "error": avail.get("detail") or "Cursor Local 不可用",
        }

    cfg = get_config()
    api_key = cfg.cursor_api_key
    primary = str(cfg.model or "composer-2.5").strip() or "composer-2.5"
    models: list[str] = [primary]
    if primary.lower() not in {"auto", "default"}:
        models.append("auto")
    deadline = time.time() + max(60, int(timeout_sec or cfg.cursor_timeout_sec))
    cwd = str(sandbox.resolve())

    try:
        from cursor_sdk import Agent, CursorAgentError  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "text": "",
            "agent_id": "",
            "run_id": "",
            "error": f"导入 cursor_sdk 失败：{exc}",
        }

    step(
        "Cursor 只读定位…" if read_only else "Cursor 本机 Agent 启动…",
        sid="cursor-local",
        state="running",
    )

    bus = _CursorStreamSink(
        sink,
        sandbox=cwd,
        max_read_tools=max_read_tools,
        read_only=read_only,
    )
    agent_id = ""
    run_id = ""
    run_obj: Any = None
    read_budget_hit = False
    write_violation_hit = False
    started = time.time()
    last_cae: Any = None
    last_error = ""

    def _cancel_run() -> None:
        nonlocal read_budget_hit
        read_budget_hit = True
        try:
            if run_obj is not None and hasattr(run_obj, "cancel"):
                run_obj.cancel()
        except Exception:
            pass

    def _abort_write() -> None:
        nonlocal write_violation_hit
        write_violation_hit = True
        _cancel_run()

    def _abort() -> str | None:
        if is_cancel_requested():
            try:
                if run_obj is not None and hasattr(run_obj, "cancel"):
                    run_obj.cancel()
            except Exception:
                pass
            return "用户已取消写码任务"
        if time.time() > deadline:
            try:
                if run_obj is not None and hasattr(run_obj, "cancel"):
                    run_obj.cancel()
            except Exception:
                pass
            return f"写码任务超时（>{timeout_sec}s），已中止"
        return None

    def _consume_stream(run: Any) -> str | None:
        # 优先 stream（含 thinking/assistant）；events 作次选
        stream_fn = getattr(run, "stream", None) or getattr(run, "events", None) or getattr(run, "messages", None)
        if not callable(stream_fn):
            return None
        try:
            for event in stream_fn():
                abort = _abort()
                if abort:
                    return abort
                try:
                    msg = getattr(event, "sdk_message", None)
                    bus.handle_message(msg if msg is not None else event)
                except Exception as exc:  # noqa: BLE001
                    _emit(
                        sink,
                        {
                            "type": "status",
                            "text": f"进度事件异常：{type(exc).__name__}: {exc}"[:240],
                        },
                    )
        except Exception as exc:  # noqa: BLE001
            _emit(sink, {"type": "status", "text": f"进度流异常：{type(exc).__name__}: {exc}"[:240]})
        return None

    def _finish_ok(reply: str) -> dict[str, Any]:
        step("Cursor 定位完成" if read_only else "Cursor 本机 Agent 完成", sid="cursor-local", state="done")
        return _with_dialog(
            bus,
            {
                "ok": True,
                "text": (reply or "").strip() or (bus.final_text or "").strip() or "Cursor 已完成本轮本机写码。",
                "agent_id": agent_id,
                "run_id": run_id,
                "error": "",
            },
        )

    for mi, model in enumerate(models):
        # 每个 model 重置总线，避免种子/失败状态污染
        bus = _CursorStreamSink(
            sink,
            sandbox=cwd,
            max_read_tools=max_read_tools,
            read_only=read_only,
        )
        bus._on_read_budget = _cancel_run
        bus._on_write_violation = _abort_write if read_only else None
        read_budget_hit = False
        write_violation_hit = False
        bus.flush_think()
        bus.seed_process(
            "正在只读定位待删文件。"
            if read_only
            else "正在启动 Cursor，开始对照工作区定位相关代码。"
        )
        _emit(
            sink,
            {
                "type": "status",
                "text": (
                    f"Cursor 只读定位（model={model}，禁止改文件）"
                    if read_only
                    else f"Cursor Local（model={model}）"
                ),
                "phase": "agent",
            },
        )

        # 每个 model 最多 2 次：瞬时 500 可重试
        for attempt in range(2):
            try:
                with Agent.create(
                    model=model,
                    api_key=api_key,
                    local=_local_agent_options(cwd),
                ) as agent:
                    agent_id = str(getattr(agent, "agent_id", None) or getattr(agent, "agentId", "") or "")
                    abort = _abort()
                    if abort:
                        return {
                            "ok": False,
                            "text": bus.final_text,
                            "agent_id": agent_id,
                            "run_id": "",
                            "error": abort,
                        }

                    send_kwargs: dict[str, Any] = {}
                    try:
                        from cursor_sdk import SendOptions  # type: ignore

                        send_kwargs["options"] = SendOptions(
                            on_delta=_safe_cb(bus.handle_delta, sink),
                            on_step=_safe_cb(bus.handle_step, sink),
                        )
                    except Exception:
                        send_kwargs = {}

                    try:
                        run_obj = agent.send(prompt, **send_kwargs) if send_kwargs else agent.send(prompt)
                    except TypeError:
                        run_obj = agent.send(prompt)
                    run_id = str(
                        getattr(run_obj, "id", None)
                        or getattr(run_obj, "run_id", None)
                        or getattr(run_obj, "runId", "")
                        or ""
                    )

                    stream_abort = _consume_stream(run_obj)
                    result = run_obj.wait()
                    _harvest_run_dialog(bus, run_obj, result)
                    status = str(getattr(result, "status", "") or "")
                    result_text = str(
                        getattr(result, "result", None) or getattr(result, "text", None) or ""
                    ).strip()
                    reply = bus.composed_public_reply()
                    if not reply.strip() and result_text:
                        reply = result_text
                    if bus.final_text:
                        _emit(sink, {"type": "replace_text", "text": bus.final_text})
                    if bus._last_delivery:
                        _emit(sink, {"type": "replace_delivery", "text": bus._last_delivery})
                    bus.flush_think(duration=int(max(0, (time.time() - started) * 1000)), finish=True)

                    if stream_abort:
                        abort = stream_abort
                    else:
                        abort = _abort()
                    if abort:
                        if read_only and looks_like_delete_plan_reply(reply):
                            return _finish_ok(reply)
                        return _with_dialog(
                            bus,
                            {
                                "ok": False,
                                "text": reply or bus.final_text,
                                "agent_id": agent_id,
                                "run_id": run_id,
                                "error": abort,
                            },
                        )

                    if read_only and (write_violation_hit or read_budget_hit) and (
                        looks_like_delete_plan_reply(reply) or _dialog_captured(bus)
                    ):
                        return _finish_ok(reply)

                    if status == "error":
                        detail = bus.failure_detail or result_text or "未知错误"
                        usage_hit = bool(_USAGE_LIMIT_RE.search(str(detail)))
                        last_error = f"Cursor Run 失败：{detail}" + (
                            "（额度用尽，将尝试 Auto）" if usage_hit and mi + 1 < len(models) else (
                                "（额度用尽，请检查 Cursor 账号或改用 Auto）" if usage_hit else ""
                            )
                        )
                        # 已有正文：即使 status=error 也交还给面板
                        if _dialog_captured(bus) or looks_like_delete_plan_reply(reply):
                            return _finish_ok(reply)
                        if usage_hit and mi + 1 < len(models):
                            _emit(
                                sink,
                                {
                                    "type": "status",
                                    "text": f"{primary} 额度不足，自动切换 model=auto 重试以获取对话框正文…",
                                },
                            )
                            break  # 下一 model
                        return _with_dialog(
                            bus,
                            {
                                "ok": False,
                                "text": reply or bus.final_text,
                                "agent_id": agent_id,
                                "run_id": run_id,
                                "error": last_error,
                            },
                        )

                    return _finish_ok(reply)
            except CursorAgentError as err:  # type: ignore[misc]
                last_cae = err
                msg = str(getattr(err, "message", None) or err or "")
                usage_hit = bool(_USAGE_LIMIT_RE.search(msg))
                last_error = f"Cursor Agent 启动失败：{_format_cursor_agent_error(err)}"
                if usage_hit and mi + 1 < len(models):
                    _emit(
                        sink,
                        {
                            "type": "status",
                            "text": f"{primary} 额度不足，自动切换 model=auto 重试…",
                        },
                    )
                    break
                if attempt == 0 and (
                    "internal" in msg.lower()
                    or getattr(err, "status", None) == 500
                    or getattr(err, "is_retryable", False)
                ):
                    _emit(sink, {"type": "status", "text": "Cursor 云端返回内部错误，正在重试启动…"})
                    time.sleep(2.0)
                    continue
                return _with_dialog(
                    bus,
                    {
                        "ok": False,
                        "text": bus.final_text,
                        "agent_id": agent_id,
                        "run_id": run_id,
                        "error": last_error,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                return _with_dialog(
                    bus,
                    {
                        "ok": False,
                        "text": bus.final_text,
                        "agent_id": agent_id,
                        "run_id": run_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
        else:
            continue
        # broke due to usage → next model
        continue

    return _with_dialog(
        bus,
        {
            "ok": False,
            "text": bus.final_text,
            "agent_id": agent_id,
            "run_id": run_id,
            "error": last_error
            or f"Cursor Agent 启动失败：{_format_cursor_agent_error(last_cae)}",
        },
    )
