"""审查发现：解析 LLM 输出、格式化为 simplified 风格终稿报告。"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

_FINDINGS_RE = re.compile(r":::code_review_findings\b", re.I)
_SEVERITIES = frozenset({"critical", "high", "medium", "low"})

# severity → 汇总报告 band（高危/中危/低危）
_SEV_TO_P = {
    "critical": "P0",
    "high": "P0",
    "medium": "P1",
    "low": "P2",
}

# 别名归一：注意 P1≠high（high 仍是阻塞级 P0）
_SEV_ALIASES = {
    "p0": "critical",
    "p1": "medium",
    "p2": "low",
    "blocker": "critical",
    "block": "critical",
    "error": "high",
    "warn": "medium",
    "warning": "medium",
    "info": "low",
    "nit": "low",
    "suggestion": "low",
}


@dataclass
class ReviewFinding:
    file: str
    line: int | None
    severity: str
    title: str
    description: str
    code_snippet: str = ""
    fix_suggestion: str = ""
    fix_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def priority(self) -> str:
        return _SEV_TO_P.get(self.severity, "P1")


def _loads_json_list(body: str) -> list[dict[str, Any]] | None:
    text = (body or "").strip()
    if not text:
        return None
    # 去掉 ```json 围栏
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|JSON)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("["), text.rfind("]")
        if a < 0 or b <= a:
            return None
        try:
            obj = json.loads(text[a : b + 1])
        except json.JSONDecodeError:
            # 容忍尾逗号
            try:
                obj = json.loads(re.sub(r",\s*([}\]])", r"\1", text[a : b + 1]))
            except json.JSONDecodeError:
                return None
    if isinstance(obj, dict) and isinstance(obj.get("findings"), list):
        obj = obj["findings"]
    if not isinstance(obj, list):
        return None
    return [x for x in obj if isinstance(x, dict)]


def _extract_findings_block(text: str) -> list[dict[str, Any]] | None:
    s = text or ""
    m = _FINDINGS_RE.search(s)
    if m:
        after = s[m.end() :].lstrip()
        close = re.search(r"\n[ \t]*:::[ \t]*(?:\n|$)", after)
        body = after[: close.start()].strip() if close else re.sub(r"\n?[ \t]*:::[ \t]*\s*$", "", after).strip()
        rows = _loads_json_list(body)
        if rows is not None:
            return rows
    # 兜底：全文找 JSON 数组（模型偶发漏 ::: 标记或包在 ```json 里）
    for m2 in re.finditer(r"```(?:json|JSON)?\s*(\[[\s\S]*?\])\s*```", s):
        rows = _loads_json_list(m2.group(1))
        if rows is not None:
            return rows
    # 裸数组：含 file/title/severity 字段
    a, b = s.find("["), s.rfind("]")
    if a >= 0 and b > a and '"file"' in s[a : b + 1] and '"title"' in s[a : b + 1]:
        rows = _loads_json_list(s[a : b + 1])
        if rows is not None:
            return rows
    return None


def _normalize_severity(raw: Any) -> str:
    sev = str(raw or "medium").strip().lower()
    sev = _SEV_ALIASES.get(sev, sev)
    if sev not in _SEVERITIES:
        sev = "medium"
    return sev


def _normalize_finding(row: dict[str, Any]) -> ReviewFinding | None:
    file = str(row.get("file") or row.get("path") or "").strip()
    title = str(row.get("title") or row.get("name") or "").strip()
    desc = str(row.get("description") or row.get("detail") or row.get("risk") or "").strip()
    if not file or not title:
        return None
    line_raw = row.get("line")
    line: int | None
    try:
        line = int(line_raw) if line_raw is not None and str(line_raw).strip() != "" else None
    except (TypeError, ValueError):
        line = None
    return ReviewFinding(
        file=file,
        line=line,
        severity=_normalize_severity(row.get("severity")),
        title=title,
        description=desc or title,
        code_snippet=str(row.get("code_snippet") or row.get("code") or "").strip()[:2000],
        fix_suggestion=str(row.get("fix_suggestion") or row.get("fix") or "").strip()[:1200],
        fix_code=str(row.get("fix_code") or "").strip()[:2000],
    )


def parse_findings(llm_text: str) -> tuple[str, list[ReviewFinding]]:
    """返回 (prose_without_fence, findings)。"""
    raw = llm_text or ""
    rows = _extract_findings_block(raw) or []
    findings: list[ReviewFinding] = []
    for row in rows:
        f = _normalize_finding(row)
        if f:
            findings.append(f)

    prose = raw
    if _FINDINGS_RE.search(prose):
        prose = re.sub(r":::code_review_findings[\s\S]*?(?:\n[ \t]*:::[ \t]*(?:\n|$)|\Z)", "", prose).strip()
    prose = re.sub(r":::code_review_findings\b", "", prose).strip()
    # 去掉兜底抽走的 json 围栏，避免污染摘要
    if findings:
        prose = re.sub(r"```(?:json|JSON)?\s*\[[\s\S]*?\]\s*```", "", prose).strip()
    return prose, findings


def prose_claims_issues(prose: str) -> bool:
    """摘要声称有问题但机器块为空时，用于触发复审。"""
    t = prose or ""
    if not t.strip():
        return False
    neg = ("未发现", "无明显", "无严重", "没有问题", "无问题", "未检出", "暂无")
    if any(x in t for x in neg) and not any(x in t for x in ("但", "不过", "然而", "除了")):
        return False
    pos = (
        "P0",
        "P1",
        "漏洞",
        "风险",
        "必须修复",
        "空指针",
        "未鉴权",
        "无鉴权",
        "明文",
        "注入",
        "越权",
        "硬编码密钥",
        "敏感信息",
        "严重",
        "高危",
    )
    return any(x in t for x in pos)


def format_findings_report(
    findings: list[ReviewFinding],
    *,
    summary: str = "",
    files_reviewed: list[str] | None = None,
    local_path: str = "",
    skill_id: str = "zr-workbuddy-code-review",
    draft_note: str = "",
    force_incomplete: bool = False,
) -> str:
    """终稿体例对齐「代码审核汇总报告」；排版紧凑（避免多余空行）。"""
    from datetime import date

    files = list(files_reviewed or [])
    buckets: dict[str, list[ReviewFinding]] = {"P0": [], "P1": [], "P2": []}
    for f in findings:
        buckets.setdefault(f.priority, []).append(f)
    n0, n1, n2 = len(buckets["P0"]), len(buckets["P1"]), len(buckets["P2"])
    total = n0 + n1 + n2

    # 单行接续，少插空行；文件列表用顿号挤在一段里
    lines: list[str] = ["代码审核汇总报告"]
    if files:
        lines.append("审核文件：" + "、".join(files))
    else:
        lines.append("审核文件：（无）")
    lines.append(f"审核日期：{date.today().isoformat()}")
    lines.append(f"审核人：Viprasol + workbuddy-gate-90（Skill `{skill_id}`）")
    if local_path:
        lines.append(f"工程路径：{local_path}")
    lines.append("---")
    lines.append("一、总体评价")

    sum_txt = (summary or "").strip()
    if sum_txt:
        sum_txt = re.sub(r"^##\s*🔍?\s*代码审核报告\s*", "", sum_txt, flags=re.I).strip()
        sum_txt = re.sub(r"(?is)\*{0,2}分批纪要\*{0,2}[\s\S]*$", "", sum_txt).strip()
        first = next((ln.strip() for ln in sum_txt.splitlines() if ln.strip()), "")
        if first and "第 " not in first and "批：" not in first:
            lines.append(first)

    if total == 0:
        lines.append("本次审核共发现 0 个问题。")
        lines.append("- 🔴 高危问题：0 处")
        lines.append("- 🟡 中危问题：0 处")
        lines.append("- 🟢 低危问题：0 处")
        lines.append(
            "本轮抽样未发现需阻塞合并的严重问题；建议结合业务场景再人工抽查关键路径。"
        )
        lines.append("---")
        lines.append("二、详细问题清单（汇总后）")
        lines.append("（无）")
        lines.append("---")
        lines.append("四、审核结论")
        if force_incomplete:
            lines.append("❌ 审查不完整（LLM 未成功完成审查，不得视为通过）")
        else:
            lines.append("✅ 审核通过（抽样范围内未发现高/中危阻塞项）")
        if draft_note:
            lines.append(f"> {draft_note}")
        return "\n".join(lines).rstrip() + "\n"

    lines.append(f"本次审核共发现 {total} 个问题，具体分布如下：")
    lines.append(f"- 🔴 高危问题：{n0} 处")
    lines.append(f"- 🟡 中危问题：{n1} 处")
    lines.append(f"- 🟢 低危问题：{n2} 处")
    if n0:
        lines.append("其中高危项须全部修复后方可合并；中危项建议合入前处理。")
    lines.append(
        "所有问题均基于已读源码/配置，方法论为 Viprasol + workbuddy-gate-90"
        "（及源码规则补种），位置与代码片段对应原始文件。"
    )
    lines.append("---")
    lines.append("二、详细问题清单（汇总后）")

    label = {
        "P0": "🔴 高危",
        "P1": "🟡 中危",
        "P2": "🟢 低危",
    }
    idx = 0
    band_items = [(b, f) for b in ("P0", "P1", "P2") for f in (buckets.get(b) or [])]
    for bi, (band, f) in enumerate(band_items):
        idx += 1
        # 用「问题 N」避免与严重度 band P0/P1/P2 混淆
        lines.append(f"{label[band]} 问题{idx} — {f.title}")
        loc = f"约第 {f.line} 行" if f.line is not None else "见相关片段"
        lines.append(f"文件：{f.file}　位置：{loc}")
        lines.append(f"问题描述：{f.description}")
        if f.code_snippet:
            lines.append("// ❌ 当前代码")
            lines.append("```")
            lines.append(f.code_snippet.rstrip())
            lines.append("```")
        if f.fix_suggestion:
            lines.append(f"修改建议：{f.fix_suggestion}")
        if f.fix_code:
            lines.append("// ✅ 正确做法")
            lines.append("```")
            lines.append(f.fix_code.rstrip())
            lines.append("```")
        if bi < len(band_items) - 1:
            lines.append("---")

    lines.append("---")
    lines.append("四、审核结论")
    if force_incomplete:
        lines.append("❌ 审查不完整（LLM 未成功完成审查，不得视为通过）")
        lines.append(f"- 当前可见问题：高危{n0} / 中危{n1} / 低危{n2}（可能仅含规则补种）。")
    elif n0:
        lines.append("❌ 审核不通过")
        lines.append(f"- 🔴 高危问题：{n0} 处，必须全部修复后方可合并。")
        if n1:
            lines.append(f"- 🟡 中危问题：{n1} 处，建议合入前优先处理。")
        if n2:
            lines.append(f"- 🟢 低危问题：{n2} 处，建议后续迭代整改。")
    elif n1:
        lines.append("⚠️ 有条件通过（存在中危项）")
        lines.append(f"- 🟡 中危问题：{n1} 处，建议合入前处理。")
        if n2:
            lines.append(f"- 🟢 低危问题：{n2} 处，建议后续迭代整改。")
    else:
        lines.append("✅ 审核通过（无高/中危；仅有低危建议项）")
        lines.append(f"- 🟢 低危问题：{n2} 处，建议后续迭代整改。")
    lines.append(f"✅ 数量核对：高危{n0} + 中危{n1} + 低危{n2} = 总问题数{total}。")
    if draft_note:
        lines.append(f"> {draft_note}")
    return "\n".join(lines).rstrip() + "\n"


def findings_to_dict(findings: list[ReviewFinding]) -> list[dict[str, Any]]:
    return [f.to_dict() for f in findings]
