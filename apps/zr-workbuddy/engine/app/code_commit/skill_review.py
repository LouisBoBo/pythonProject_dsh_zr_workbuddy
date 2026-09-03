"""提交批审：commit-batch-review Skill（经 llm_freeform，非 LangChain / 非全量审码）。"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from ..code_review.config import ALLOWED_SUFFIXES, DOC_OR_STYLE_SUFFIXES, CodeReviewConfig
from ..code_review.local_files import read_review_files
from ..code_dev.sandbox import is_sensitive_rel
from ..config_store import load_config

_MAX_FILES = 40
_MAX_CHARS_PER_FILE = 12_000
_logger = logging.getLogger("code_commit.skill_review")

# apps/zr-workbuddy/engine/app/code_commit → 仓库根
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SKILL_DIR = _REPO_ROOT / ".dsh" / "skills" / "zr-workbuddy-commit-batch-review"


def _norm_rel(rel: str) -> str:
    r = (rel or "").replace("\\", "/").strip()
    while r.startswith("./"):
        r = r[2:]
    return r.lstrip("/")


def is_functional_source_rel(rel: str) -> bool:
    """业务/功能源码：白名单后缀、非文档样式、非敏感（供批审 LLM 深读）。"""
    r = _norm_rel(rel)
    if not r or is_sensitive_rel(r):
        return False
    suf = Path(r).suffix.lower()
    if suf in DOC_OR_STYLE_SUFFIXES:
        return False
    return suf in ALLOWED_SUFFIXES


# 可随本批提交、但不走功能源码深审的后缀（文档 / SPA 壳）
_COMMIT_EXTRA_SUFFIXES = frozenset({".md", ".mdx", ".html", ".htm"})
# 仓库元数据（无后缀或特殊名）
_COMMIT_META_BASENAMES = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".npmrc",
        ".nvmrc",
    }
)


def is_committable_rel(rel: str) -> bool:
    """人触发提交可纳入的路径：功能源码 + 文档/Skill/HTML 壳 + 常见仓库元数据。

    仍排除敏感路径；样式/图片/锁等不纳入（避免把无关噪音塞进本批）。
    """
    r = _norm_rel(rel)
    if not r or is_sensitive_rel(r):
        return False
    if is_functional_source_rel(r):
        return True
    base = Path(r).name.lower()
    if base in _COMMIT_META_BASENAMES:
        return True
    suf = Path(r).suffix.lower()
    return suf in _COMMIT_EXTRA_SUFFIXES


def _estimate_tokens(text: str) -> int:
    n = len(text or "")
    return max(1, (n + 1) // 2) if n else 0


def _sync_await(coro: Any, *, timeout: float = 180) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=timeout)


def load_skill_bundle() -> str:
    parts: list[str] = []
    skill_md = _SKILL_DIR / "SKILL.md"
    if skill_md.is_file():
        parts.append(skill_md.read_text(encoding="utf-8"))
    for name in ("checklist.md", "output-schema.md"):
        p = _SKILL_DIR / "references" / name
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


def _read_batch_contents(root: Path, synced: list[str]) -> list[dict[str, str]]:
    paths = [
        p
        for p in (_norm_rel(x) for x in synced if str(x).strip())
        if p and is_functional_source_rel(p)
    ][:_MAX_FILES]
    if not paths:
        return []
    cfg = CodeReviewConfig(
        max_files=_MAX_FILES,
        max_file_bytes=_MAX_CHARS_PER_FILE * 4,
        max_total_bytes=_MAX_CHARS_PER_FILE * _MAX_FILES,
    )
    packed, _warnings, _total = read_review_files(root, paths, cfg)
    out: list[dict[str, str]] = []
    for item in packed:
        if not isinstance(item, dict):
            continue
        path = _norm_rel(str(item.get("path") or ""))
        body = str(item.get("content") or "")
        if not path or not is_functional_source_rel(path):
            continue
        if "\x00" in body[:4000]:
            continue
        if len(body) > _MAX_CHARS_PER_FILE:
            body = body[:_MAX_CHARS_PER_FILE] + "\n…(截断)"
        out.append({"path": path, "content": body})
    return out


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_skill_result(
    data: dict[str, Any],
    *,
    synced: list[str],
    llm_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    findings_in = data.get("findings") if isinstance(data.get("findings"), list) else []
    findings: list[dict[str, Any]] = []
    for f in findings_in:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity") or "P2").upper()
        if sev not in {"P0", "P1", "P2"}:
            sev = "P2"
        blocking = bool(f.get("blocking"))
        if sev in {"P0", "P1"}:
            blocking = True
        findings.append(
            {
                "severity": sev,
                "path": _norm_rel(str(f.get("path") or "")),
                "rule": str(f.get("rule") or "commit-batch-review")[:80],
                "message": str(f.get("message") or "")[:300],
                "blocking": blocking,
            }
        )

    scans_in = data.get("file_scans") if isinstance(data.get("file_scans"), list) else []
    file_scans: list[dict[str, Any]] = []
    for s in scans_in:
        if not isinstance(s, dict):
            continue
        file_scans.append(
            {
                "path": _norm_rel(str(s.get("path") or "")),
                "status": "blocked" if str(s.get("status") or "").lower() == "blocked" else "pass",
                "steps": [str(x)[:200] for x in (s.get("steps") or []) if str(x).strip()][:8],
                "issues": [str(x)[:200] for x in (s.get("issues") or []) if str(x).strip()][:8],
            }
        )

    seen_paths = {s["path"] for s in file_scans if s.get("path")}
    for rel in synced:
        if rel not in seen_paths:
            file_scans.append({"path": rel, "status": "pass", "steps": ["已纳入本批范围"], "issues": []})

    blocking = [f for f in findings if f.get("blocking") or f.get("severity") in {"P0", "P1"}]
    warnings = [f for f in findings if f not in blocking]
    verdict = str(data.get("verdict") or "").lower()
    if not verdict:
        verdict = "blocked" if blocking else ("warn" if warnings else "pass")

    summary = str(data.get("summary") or "").strip()
    if not summary:
        if blocking:
            summary = f"提交批审：{len(blocking)} 条阻断、{len(warnings)} 条警告 —— 禁止提交"
        elif warnings:
            summary = f"提交批审：无阻断，{len(warnings)} 条警告 —— 确认后可提交"
        else:
            summary = "提交批审：未发现阻断或警告 —— 可提交"

    steps = data.get("process_steps") if isinstance(data.get("process_steps"), list) else []
    process_steps = [str(x).strip() for x in steps if str(x).strip()][:20]

    out: dict[str, Any] = {
        "ok": True,
        "provider": "commit-batch-review-skill",
        "review_method": "commit-batch-review Skill（门禁批审；非全量审码报告）",
        "files_reviewed": len(synced),
        "findings": findings[:50],
        "file_scans": file_scans[:80],
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "can_commit": not blocking,
        "summary": summary,
        "verdict": verdict,
        "process_steps": process_steps,
        "checks": [
            "Skill：zr-workbuddy-commit-batch-review（提交批审专用）",
            "检查面：敏感路径 / 注入·RCE / 密钥 / 认证 / 正确性（本批）",
            "P0/P1 阻断；P2 警告",
        ],
        "scope_label": f"提交批审 Skill · 本批 {len(synced)} 个文件（非全仓审码）",
    }
    if isinstance(llm_usage, dict) and llm_usage:
        out["llm_usage"] = llm_usage
    return out


def run_commit_batch_skill_review(
    workspace: Path | str,
    synced_files: list[str],
) -> dict[str, Any] | None:
    """调用 llm_freeform + 批审 Skill；失败返回 None（由 gate 降级正则）。"""
    root = Path(workspace).expanduser().resolve()
    synced = [_norm_rel(str(p)) for p in (synced_files or []) if str(p).strip()]
    synced = list(dict.fromkeys(synced))[:_MAX_FILES]
    if not synced:
        return _normalize_skill_result(
            {
                "verdict": "pass",
                "summary": "提交批审：无待审文件",
                "process_steps": ["① 本批无文件需审"],
                "findings": [],
                "file_scans": [],
            },
            synced=synced,
        )

    contents = _read_batch_contents(root, synced)
    if not contents:
        return None

    bundle = load_skill_bundle()
    if not bundle.strip():
        return None

    cfg = load_config()
    llm_cfg = cfg.get("deepseek") or {}
    from ..health import llm_ready

    if not llm_ready(cfg):
        return None

    from ..nl_engine import llm_freeform

    model_name = str(llm_cfg.get("model") or "unknown")
    files_blob = json.dumps(contents, ensure_ascii=False)
    system = (
        bundle
        + "\n\n你是提交批审引擎。严格按 output-schema 只输出一个 JSON 对象，不要 Markdown 报告。"
    )
    user = (
        f"工作区：{root}\n本批文件数：{len(synced)}\n"
        f"文件与内容（JSON）：\n{files_blob}\n\n"
        "请完成提交批审并只输出 JSON。"
    )
    t0 = time.monotonic()
    try:
        text = _sync_await(
            llm_freeform(
                system,
                user,
                llm_cfg,
                max_tokens=4096,
                timeout=120,
                temperature=0.2,
                no_cache=True,
            ),
            timeout=150,
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        _logger.warning("commit-batch-review LLM 失败: %s (%sms)", exc, elapsed_ms)
        return None
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    if not text:
        return None

    est_in = _estimate_tokens(system) + _estimate_tokens(user)
    est_out = _estimate_tokens(text)
    usage = {
        "model": model_name,
        "file_count": len(contents),
        "prompt_chars": len(system) + len(user),
        "completion_chars": len(text or ""),
        "estimated_prompt_tokens": est_in,
        "estimated_completion_tokens": est_out,
        "estimated_total_tokens": est_in + est_out,
        "elapsed_ms": elapsed_ms,
        "source": "estimate",
    }
    _logger.info(
        "[commit-batch-review] model=%s files=%s elapsed_ms=%s",
        model_name,
        len(contents),
        elapsed_ms,
    )

    parsed = _extract_json(text)
    if not parsed:
        return None
    return _normalize_skill_result(parsed, synced=synced, llm_usage=usage)
