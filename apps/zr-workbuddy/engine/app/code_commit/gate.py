"""本机提交门禁：对本轮待提交文件做批审（仅 findings 列表，非全量审码报告）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# 敏感路径：直接阻断提交
_BLOCK_BASENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}
_BLOCK_SUFFIXES = (".pem", ".p12", ".pfx", ".key")
_BLOCK_NAME_RE = re.compile(
    r"(^|/)\.env(\.|$)|(secret|credential|private.?key)",
    re.I,
)

_CONTENT_P0: list[tuple[str, re.Pattern[str], str]] = [
    (
        "dangerous-eval",
        re.compile(r"\beval\s*\("),
        "出现 eval 调用，存在任意代码执行风险",
    ),
    (
        "java-sql-string-concat",
        re.compile(
            r"(createStatement\s*\(|\.execute(Query|Update)?\s*\(\s*[\"'][^\"']*[\"']\s*\+)",
            re.I,
        ),
        "疑似 SQL 字符串拼接，存在注入风险",
    ),
]
_CONTENT_P1: list[tuple[str, re.Pattern[str], str]] = [
    (
        "hardcoded-secret",
        re.compile(
            r"(password|passwd|secret|api[_-]?key)\s*=\s*[\"'][^\"']{4,}[\"']",
            re.I,
        ),
        "疑似硬编码口令/密钥（严重风险，禁止提交）",
    ),
]


def _norm_rel(rel: str) -> str:
    r = (rel or "").replace("\\", "/").strip()
    while r.startswith("./"):
        r = r[2:]
    return r.lstrip("/")


def _is_blocked_path(rel: str) -> bool:
    r = _norm_rel(rel)
    if not r:
        return False
    base = Path(r).name
    if base in _BLOCK_BASENAMES:
        return True
    lower = base.lower()
    for suf in _BLOCK_SUFFIXES:
        if lower.endswith(suf):
            return True
    if _BLOCK_NAME_RE.search(r):
        return True
    return False


def _read_text(root: Path, rel: str, max_bytes: int = 200_000) -> str:
    path = (root / _norm_rel(rel)).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return ""
    if not path.is_file():
        return ""
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    if b"\x00" in data[:8000]:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _apply_content_regex(
    root: Path,
    synced: list[str],
    findings: list[dict[str, Any]],
    file_scans: list[dict[str, Any]],
) -> None:
    scan_by_path = {s["path"]: s for s in file_scans}
    for rel in synced:
        scan = scan_by_path.get(rel)
        if not scan or scan.get("status") == "blocked":
            continue
        text = _read_text(root, rel)
        if not text:
            scan["steps"].append("② 内容规则：跳过（不可读或非文本）")
            continue
        content_ok = True
        for rule_id, pat, msg in _CONTENT_P0:
            if pat.search(text):
                findings.append(
                    {
                        "severity": "P0",
                        "path": rel,
                        "rule": rule_id,
                        "message": msg,
                        "blocking": True,
                    }
                )
                scan["steps"].append(f"② 内容 P0：{msg}")
                scan["status"] = "blocked"
                scan["issues"].append(msg)
                content_ok = False
        for rule_id, pat, msg in _CONTENT_P1:
            if pat.search(text):
                findings.append(
                    {
                        "severity": "P1",
                        "path": rel,
                        "rule": rule_id,
                        "message": msg,
                        "blocking": True,
                    }
                )
                scan["steps"].append(f"② 内容 P1：{msg}")
                scan["status"] = "blocked"
                scan["issues"].append(msg)
                content_ok = False
        if content_ok and len(scan["steps"]) == 1:
            scan["steps"].append("② 内容规则：通过")


def run_commit_review_gate(
    workspace: Path | str,
    synced_files: list[str],
    *,
    allow_blocked_override: bool = False,
    use_skill_review: bool = True,
) -> dict[str, Any]:
    """对本轮待提交文件做门禁。

    优先级：commit-batch-review Skill（LLM+JSON）→ 本地 path+content 正则。
    仅 P0/P1 阻断 can_commit；不输出全量「代码审核汇总报告」。
    """
    root = Path(workspace).expanduser().resolve()
    synced = [_norm_rel(str(p)) for p in (synced_files or []) if str(p).strip()]
    synced = [p for p in synced if p]
    synced = list(dict.fromkeys(synced))[:80]

    provider = "path+content"
    review_method = "规则扫描：敏感路径 + 内容正则（降级）"
    process_steps: list[str] = []

    findings: list[dict[str, Any]] = []
    file_scans: list[dict[str, Any]] = []

    for rel in synced:
        scan: dict[str, Any] = {"path": rel, "steps": [], "status": "pass", "issues": []}
        if _is_blocked_path(rel):
            findings.append(
                {
                    "severity": "P0",
                    "path": rel,
                    "rule": "sensitive-path",
                    "message": f"敏感路径不应提交：{rel}",
                    "blocking": True,
                }
            )
            scan["steps"].append("① 敏感路径：未通过")
            scan["status"] = "blocked"
            scan["issues"].append("敏感路径")
        else:
            scan["steps"].append("① 敏感路径：通过")
        file_scans.append(scan)

    skill_result: dict[str, Any] | None = None
    if use_skill_review and synced:
        try:
            from .skill_review import run_commit_batch_skill_review

            skill_result = run_commit_batch_skill_review(root, synced)
        except Exception:
            skill_result = None

    if skill_result and skill_result.get("ok"):
        provider = str(skill_result.get("provider") or "commit-batch-review-skill")
        review_method = str(skill_result.get("review_method") or "")
        process_steps = list(skill_result.get("process_steps") or [])
        for f in skill_result.get("findings") or []:
            if isinstance(f, dict):
                findings.append(f)
        scan_by_path = {s["path"]: s for s in file_scans}
        for s in skill_result.get("file_scans") or []:
            if not isinstance(s, dict):
                continue
            p = _norm_rel(str(s.get("path") or ""))
            if not p:
                continue
            local = scan_by_path.get(p)
            if local and local.get("status") == "blocked":
                s = {
                    **s,
                    "status": "blocked",
                    "issues": list(local.get("issues") or []) + list(s.get("issues") or []),
                }
            scan_by_path[p] = {
                "path": p,
                "status": s.get("status") or "pass",
                "steps": list(s.get("steps") or []),
                "issues": list(s.get("issues") or []),
            }
        file_scans = list(scan_by_path.values())
        # Skill 只追加 findings，不得跳过本地内容正则（防漏报密钥 / eval）
        _apply_content_regex(root, synced, findings, file_scans)
        if "本地内容规则" not in review_method:
            review_method = (review_method or "Skill") + " + 本地内容规则（强制）"
    else:
        provider = "path+content"
        review_method = (
            "本地兜底正则（Skill 不可用或已关闭）"
            if use_skill_review
            else "本地兜底正则（Skill 已关闭）"
        )
        _apply_content_regex(root, synced, findings, file_scans)

    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for f in findings:
        key = f"{f.get('path')}|{f.get('rule')}|{f.get('message')}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    findings = uniq[:50]

    blocking = [
        f
        for f in findings
        if f.get("blocking") or str(f.get("severity") or "").upper() in {"P0", "P1"}
    ]
    warnings = [f for f in findings if f not in blocking]
    can_commit = (not blocking) or bool(allow_blocked_override)

    if not synced:
        review_method = "规则扫描：无待审文件"
        file_scans = []

    verdict = "pass"
    # 摘要必须以合并后的阻断/警告为准；Skill 原文案不得覆盖本地补扫出的 P0/P1
    if blocking:
        summary = f"提交批审：{len(blocking)} 条阻断、{len(warnings)} 条警告 —— 禁止提交"
        verdict = "blocked"
    elif warnings:
        summary = f"提交批审：无阻断，{len(warnings)} 条警告 —— 确认后可提交"
        verdict = "warn"
    else:
        summary = "提交批审：未发现阻断或警告 —— 可提交"
        verdict = "pass"

    if blocking:
        can_commit = bool(allow_blocked_override)
    elif warnings and verdict == "pass":
        verdict = "warn"

    checks = ["敏感路径（.env / 密钥文件等）→ 阻断"]
    if provider.startswith("commit-batch-review"):
        checks.extend(
            [
                "Skill：commit-batch-review（本批门禁）",
                "正确性 / 安全 / 注入 / 密钥 / 认证（本批）",
                "P0/P1 阻断；P2 警告",
            ]
        )
    else:
        checks.extend(
            [
                "内容规则：eval / SQL 拼接（P0）→ 阻断",
                "内容规则：硬编码口令/密钥（P1）→ 阻断",
            ]
        )

    return {
        "ok": True,
        "provider": provider,
        "review_method": review_method,
        "files_reviewed": len(synced),
        "findings": findings,
        "file_scans": file_scans,
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "can_commit": can_commit,
        "allow_blocked_override": bool(allow_blocked_override),
        "summary": summary,
        "verdict": verdict,
        "checks": checks,
        "reviewed_files": synced[:40],
        "scope": "batch_only",
        "scope_label": (
            str(skill_result.get("scope_label"))
            if skill_result and skill_result.get("scope_label")
            else f"提交批审 · 本批 {len(synced)} 个文件（非全仓审码）"
        ),
        "process_steps": process_steps,
        **(
            {"llm_usage": skill_result["llm_usage"]}
            if skill_result and isinstance(skill_result.get("llm_usage"), dict)
            else {}
        ),
    }
