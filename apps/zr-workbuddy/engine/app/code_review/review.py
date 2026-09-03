"""LLM 本机审码：分批直读 → 按 Viprasol Skill 审查 → 汇总终稿。

方法论来自 `.dsh/skills/zr-workbuddy-code-review`（与 simplified 同源），禁止自造检查清单。
流程对齐 simplified ide-code-review：list → read_batch → ## 🔍 代码审核报告。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from ..config_store import load_config
from ..nl_engine import llm_freeform
from .enrich import merge_findings, seed_findings_from_files
from .findings import (
    ReviewFinding,
    format_findings_report,
    parse_findings,
    prose_claims_issues,
)
from .local_files import (
    is_security_hot_file,
    read_review_files,
    select_files_for_review,
)
from .skill_prompt import build_review_system_prompt
from .workspace import resolve_scope_root, validate_review_root

# 40 文件：旧=8 批串行≈8×单批耗时；现=5 批、最多 3 路并行≈2～3×单批
BATCH_SIZE = 8
PARALLEL_BATCHES = 3
REVIEW_TEMPERATURE = 0.2
REVIEW_TIMEOUT = 120.0
# reasoner 模型会先占 reasoning_tokens；过小会导致 content 为空、LLM findings=0
REVIEW_MAX_TOKENS = 8192
_SOURCE_SUFFIXES = (
    ".py",
    ".vue",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".java",
    ".cs",
    ".go",
    ".rs",
)


def _load_llm_cfg() -> dict[str, Any] | None:
    cfg = load_config()
    llm = cfg.get("deepseek") or {}
    provider = (llm.get("provider") or "deepseek").lower()
    if provider == "none":
        return None
    if provider == "deepseek" and not (llm.get("api_key") or "").strip():
        return None
    if provider == "ollama" and not (llm.get("model") or "").strip():
        return None
    return llm


def _chunk(items: list[Any], size: int) -> list[list[Any]]:
    n = max(1, int(size or BATCH_SIZE))
    return [items[i : i + n] for i in range(0, len(items), n)] if items else []


def _batch_has_hot_files(files: list[dict[str, Any]]) -> bool:
    return any(is_security_hot_file(str(p.get("path") or "")) for p in files)


def _batch_has_source_code(files: list[dict[str, Any]]) -> bool:
    return any(
        str(p.get("path") or "").lower().endswith(_SOURCE_SUFFIXES) for p in files
    )


def _build_batch_payload(
    *,
    local_path: str,
    scope: str,
    focus: str,
    batch_index: int,
    batch_count: int,
    files: list[dict[str, Any]],
    retry_hint: str = "",
    fresh_id: str = "",
) -> str:
    lines = [
        f"【工程根目录】{local_path}",
        f"【审阅范围】{scope or '（整仓按优先级采样）'}",
        f"【批次】第 {batch_index + 1}/{batch_count} 批（本批 {len(files)} 个文件）",
        "【说明】请严格按 system 中的 Viprasol + workbuddy-gate-90 审查本批 FILE。",
        "【硬要求】有真实风险必须写入 :::code_review_findings；禁止无脑输出空数组。",
        "【禁止缓存】必须基于下方 FILE 正文当场重审；禁止复用历史结论或只复述规则补种结果。",
    ]
    if fresh_id:
        lines.append(f"【本轮审码 ID】{fresh_id}（每次运行唯一，勿当作可跳过标记）")
    if focus.strip():
        lines.append(f"【审查重点】{focus.strip()}")
    if retry_hint.strip():
        lines.append(f"【系统纠偏】{retry_hint.strip()}")
    if _batch_has_hot_files(files):
        lines.append(
            "【本批含安全热文件】请重点查：公网 URL、明文 HTTP、缺 securitySchemes/"
            "鉴权、CORS *、硬编码密钥、匿名可调用接口。"
        )
    lines.append("")
    for item in files:
        rel = item["path"]
        trunc = "（内容已截断）" if item.get("truncated") else ""
        lines.append(f"===== FILE: {rel} {trunc} =====")
        lines.append(item.get("content") or "")
        lines.append("")
    return "\n".join(lines)


def _dedupe_findings(items: list[ReviewFinding]) -> list[ReviewFinding]:
    seen: set[tuple[str, str, int | None]] = set()
    out: list[ReviewFinding] = []
    for f in items:
        key = (f.file, f.title, f.line)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _step(step_id: str, title: str, state: str, **extra: Any) -> dict[str, Any]:
    ev = {"type": "step", "id": step_id, "title": title, "state": state}
    ev.update(extra)
    return ev


async def _llm_review_once(
    system: str, user: str, llm_cfg: dict[str, Any]
) -> tuple[str, list[ReviewFinding], str | None]:
    """返回 (prose, findings, raw_or_none)。raw 为 None 表示 LLM 调用失败。"""
    raw = await llm_freeform(
        system,
        user,
        llm_cfg=llm_cfg,
        max_tokens=REVIEW_MAX_TOKENS,
        timeout=REVIEW_TIMEOUT,
        temperature=REVIEW_TEMPERATURE,
        no_cache=True,
    )
    if raw is None:
        return "", [], None
    prose, findings = parse_findings(raw)
    return prose, findings, raw


async def _review_batch(
    *,
    system: str,
    llm_cfg: dict[str, Any],
    local_path: str,
    scope: str,
    focus: str,
    batch_index: int,
    batch_count: int,
    batch_files: list[dict[str, Any]],
    fresh_id: str = "",
) -> tuple[str, list[ReviewFinding], list[str], bool]:
    """返回 (prose, findings, warnings, llm_responded)。"""
    warnings: list[str] = []
    user = _build_batch_payload(
        local_path=local_path,
        scope=scope,
        focus=focus,
        batch_index=batch_index,
        batch_count=batch_count,
        files=batch_files,
        fresh_id=fresh_id,
    )
    prose, findings, raw = await _llm_review_once(system, user, llm_cfg)
    llm_responded = raw is not None
    if raw is None:
        warnings.append(f"第 {batch_index + 1} 批 LLM 无响应，已跳过该批模型审查")

    need_retry = False
    hint = ""
    if raw is not None and not findings:
        if _batch_has_hot_files(batch_files):
            need_retry = True
            hint = (
                "本批含 OpenAPI/部署/鉴权等热文件，上一轮 findings 为空。"
                "请重新审查公网暴露、明文 HTTP、缺鉴权、CORS、密钥泄露；"
                "确有风险必须输出非空 :::code_review_findings，不得空数组敷衍。"
            )
        elif prose_claims_issues(prose):
            need_retry = True
            hint = (
                "上一轮摘要似乎提到了风险，但 :::code_review_findings 为空或无法解析。"
                "请只输出中文摘要 + 合法机器块；每条须含 file/title/severity。"
            )
        elif _batch_has_source_code(batch_files):
            need_retry = True
            hint = (
                "上一轮对本批业务源码输出了空 findings。"
                "请重新审查正确性、安全、性能与可维护性；"
                "真实的中危/低危（命名、异常处理、重复逻辑、缺校验等）也必须写入；"
                "仅当本批确实无明显问题时才可再次输出 []。"
            )

    if need_retry:
        user2 = _build_batch_payload(
            local_path=local_path,
            scope=scope,
            focus=focus,
            batch_index=batch_index,
            batch_count=batch_count,
            files=batch_files,
            retry_hint=hint,
            fresh_id=f"{fresh_id}-retry" if fresh_id else "retry",
        )
        prose2, findings2, raw2 = await _llm_review_once(system, user2, llm_cfg)
        if raw2 is None:
            warnings.append(f"第 {batch_index + 1} 批复审 LLM 无响应")
        else:
            llm_responded = True
            if findings2 or (prose2 and not prose):
                prose, findings = prose2 or prose, findings2 or findings
            elif findings2:
                findings = findings2
    return prose, findings, warnings, llm_responded


async def iter_llm_review(
    *,
    local_path: str,
    scope: str = "",
    files: list[str] | None = None,
    focus: str = "",
    cfg,
) -> AsyncIterator[dict[str, Any]]:
    """带进度事件的分批审码；最后一条 type=done。"""
    yield _step("validate", "校验工程路径", "running")
    check = validate_review_root(local_path)
    if not check.get("ok"):
        yield _step("validate", "路径无效", "error")
        yield {
            "type": "done",
            "ok": False,
            "detail": check.get("error") or "路径无效",
            "reply": check.get("error") or "路径无效",
        }
        return

    root = Path(check["path"])
    explicit = files
    if check.get("is_file"):
        root = root.parent
        explicit = [Path(check["path"]).name]
    yield _step("validate", f"路径可用：{root}", "done")

    scope_root, scope_err = resolve_scope_root(root, scope)
    if scope_err:
        yield _step("list", scope_err, "error")
        yield {"type": "done", "ok": False, "detail": scope_err, "reply": scope_err}
        return

    yield _step("list", "正在筛选功能源码…", "running")
    selected, sel_warn = select_files_for_review(
        root,
        scope_root=scope_root,
        explicit_files=explicit,
        cfg=cfg,
    )
    if not selected:
        msg = "；".join(sel_warn) or "没有可审阅的功能源码（已排除文档/样式/vendor）"
        yield _step("list", "未找到功能源码", "error")
        yield {
            "type": "done",
            "ok": False,
            "detail": msg,
            "reply": (
                "## 🔍 代码审核报告\n\n"
                f"- **工程**：`{root}`\n\n"
                f"**无法开始审查**：{msg}\n"
            ),
            "warnings": sel_warn,
            "files_reviewed": [],
            "file_count": 0,
        }
        return

    batches_paths = _chunk(selected, BATCH_SIZE)
    yield {
        "type": "status",
        "detail": f"已筛选本机工程功能源码 {len(selected)} 个，分 {len(batches_paths)} 批审核…",
    }
    yield _step("list", f"已筛选 {len(selected)} 个源码文件 · {len(batches_paths)} 批", "done")

    yield _step("read", "正在读取源码…", "running")
    payloads, read_warn, total_bytes = read_review_files(root, selected, cfg)
    warnings = list(sel_warn) + list(read_warn)
    if not payloads:
        msg = "；".join(warnings) or "读取文件失败"
        yield _step("read", "读取失败", "error")
        yield {"type": "done", "ok": False, "detail": msg, "reply": msg, "warnings": warnings}
        return
    yield {
        "type": "status",
        "detail": f"已读取 {len(payloads)} 个文件（约 {total_bytes} 字节）…",
    }
    yield _step("read", f"已读取 {len(payloads)} 个文件", "done")

    # 对齐 simplified enrich：规则补种（空 LLM ≠ 无问题）
    # 注意：过程中不要推「完整报告」草稿，否则用户会以为已出终稿/有缓存
    seeded = seed_findings_from_files(payloads)
    files_reviewed = [p["path"] for p in payloads]
    if seeded:
        yield {
            "type": "status",
            "detail": (
                f"规则预检命中 {len(seeded)} 条（待与 LLM 结果合并）；"
                f"已读 {len(files_reviewed)} 个文件，正在调用 Viprasol Skill…"
            ),
        }

    llm_cfg = _load_llm_cfg()
    if not llm_cfg:
        msg = "LLM 未配置或未就绪，无法出审查报告"
        # 仍可用规则 findings 出报告
        if seeded:
            reply = format_findings_report(
                seeded,
                summary="LLM 未就绪，本报告仅含源码规则补种结果。",
                files_reviewed=files_reviewed,
                local_path=str(root),
            )
            yield _step("llm", "LLM 未就绪，已用规则 findings 出报告", "done")
            yield {
                "type": "done",
                "ok": True,
                "reply": reply,
                "summary": "规则补种",
                "findings": [f.to_dict() for f in seeded],
                "files_reviewed": [p["path"] for p in payloads],
                "file_count": len(payloads),
                "bytes_read": total_bytes,
                "batch_count": 0,
                "skill": "zr-workbuddy-code-review",
                "warnings": warnings + [msg],
                "local_path": str(root),
                "scope": scope or "",
                "focus": focus or "",
                "source": "code_review",
                "data_source": "code_review",
                "enrich_count": len(seeded),
            }
            return
        yield _step("llm", msg, "error")
        yield {
            "type": "done",
            "ok": False,
            "detail": msg,
            "reply": "请先在配置中心配置 LLM 引擎（DeepSeek / Ollama）",
        }
        return

    system = build_review_system_prompt()
    # 每轮唯一 ID：打断供应商 prompt cache，并写入报告供核对「非复用旧结果」
    fresh_id = f"cr-run-{uuid.uuid4().hex[:12]}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    all_findings: list[ReviewFinding] = []
    batch_notes: list[str] = []
    content_batches = _chunk(payloads, BATCH_SIZE)
    batch_count = len(content_batches)
    yield {
        "type": "status",
        "detail": (
            f"全量重审 {fresh_id} · 并行 {batch_count} 批"
            f"（每批≤{BATCH_SIZE} 文件，并发 {min(PARALLEL_BATCHES, batch_count)}）…"
        ),
    }
    yield _step(
        "llm",
        f"并行审核中 0/{batch_count} 批…",
        "running",
    )

    sem = asyncio.Semaphore(max(1, PARALLEL_BATCHES))

    async def _run_one(bi: int, batch_files: list[dict[str, Any]]):
        async with sem:
            prose, findings, batch_warn, llm_ok = await _review_batch(
                system=system,
                llm_cfg=llm_cfg,
                local_path=str(root),
                scope=scope,
                focus=focus,
                batch_index=bi,
                batch_count=batch_count,
                batch_files=batch_files,
                fresh_id=fresh_id,
            )
            return bi, batch_files, prose, findings, batch_warn, llm_ok

    tasks = [
        asyncio.create_task(_run_one(bi, batch_files))
        for bi, batch_files in enumerate(content_batches)
    ]
    finished = 0
    llm_ok_batches = 0
    llm_fail_batches = 0
    for fut in asyncio.as_completed(tasks):
        bi, batch_files, prose, findings, batch_warn, llm_ok = await fut
        finished += 1
        if llm_ok:
            llm_ok_batches += 1
        else:
            llm_fail_batches += 1
        warnings.extend(batch_warn)
        all_findings.extend(findings)
        note = (prose or "").strip().splitlines()
        if note:
            batch_notes.append(f"第 {bi + 1} 批：{note[0][:120]}")
        elif not findings:
            paths = "、".join(p["path"] for p in batch_files[:3])
            batch_notes.append(f"第 {bi + 1} 批（{paths}…）：模型未返回 findings")
        merged_n = len(merge_findings(all_findings, seeded))
        yield _step(
            "llm",
            f"并行审核中 {finished}/{batch_count} 批…",
            "running",
        )
        yield {
            "type": "status",
            "detail": (
                f"已完成 {finished}/{batch_count} 批 · LLM 暂计 {len(all_findings)} 条"
                f" · 合并后约 {merged_n} 条（报告将在全部批次结束后生成）"
            ),
        }

    # 全空但有热文件：加审（规则已有则跳过加审以省时）
    hot_payloads = [p for p in payloads if is_security_hot_file(str(p.get("path") or ""))]
    if not all_findings and hot_payloads and not seeded:
        yield {
            "type": "status",
            "detail": f"首轮无 findings，正在对 {len(hot_payloads)} 个安全热文件加审…",
        }
        yield _step("llm", f"安全热文件加审（{len(hot_payloads)}）…", "running")
        for bi, batch_files in enumerate(_chunk(hot_payloads, max(2, BATCH_SIZE - 2))):
            prose, findings, batch_warn, llm_ok = await _review_batch(
                system=system,
                llm_cfg=llm_cfg,
                local_path=str(root),
                scope=scope,
                focus=(focus + " 重点：鉴权、公网暴露、明文传输、密钥").strip(),
                batch_index=bi,
                batch_count=1,
                batch_files=batch_files,
                fresh_id=f"{fresh_id}-hot",
            )
            warnings.extend(batch_warn)
            if llm_ok:
                llm_ok_batches += 1
            else:
                llm_fail_batches += 1
            all_findings.extend(findings)
            if findings:
                break

    llm_count = len(all_findings)
    all_findings = merge_findings(all_findings, seeded)
    all_findings = _dedupe_findings(all_findings)

    llm_total_attempts = llm_ok_batches + llm_fail_batches
    all_llm_failed = llm_total_attempts > 0 and llm_ok_batches == 0
    if all_llm_failed:
        warnings.append(
            "全部 LLM 批次调用失败或无响应：本报告不可作为完整审查结论（最多仅含规则补种）。"
        )
    elif llm_count == 0 and seeded:
        warnings.append(
            "LLM 已响应但未产出 findings；报告问题主要来自规则补种，请人工复核业务源码。"
        )
    elif llm_count == 0 and not seeded:
        warnings.append(
            "LLM 已响应且规则补种为空：抽样范围内未检出机器可确认问题，仍建议人工抽查关键路径。"
        )

    yield _step("llm", f"各批已完成（共 {batch_count} 批 · 并行 · Skill: Viprasol）", "done")

    yield _step("report", "各批已完成，正在汇总完整审核报告…", "running")
    summary = (
        f"已按 Viprasol + workbuddy-gate-90 **全量重审** {len(files_reviewed)} 个功能源码文件"
        f"（{batch_count} 批并行，审码 ID `{fresh_id}`，无结果缓存）。"
        f"LLM 产出 {llm_count} 条；规则补种 {len(seeded)} 条；合并去重后 {len(all_findings)} 条。"
    )
    if all_llm_failed:
        summary = (
            f"⚠️ LLM 全部失败（审码 ID `{fresh_id}`）。"
            f"已读 {len(files_reviewed)} 文件；规则补种 {len(seeded)} 条。"
            "不可视为完整企业级审查通过。"
        )
    if batch_notes:
        yield {
            "type": "status",
            "detail": "分批纪要已收拢，正在生成终稿报告…",
        }
    reply = format_findings_report(
        all_findings,
        summary=summary,
        files_reviewed=files_reviewed,
        local_path=str(root),
        force_incomplete=all_llm_failed,
    )
    if warnings:
        reply = (
            reply.rstrip()
            + "\n\n---\n⚠️ 审查告警：\n"
            + "\n".join(f"- {w}" for w in warnings[:30])
            + "\n"
        )
    yield _step("report", "审核报告已生成", "done")
    yield {
        "type": "done",
        "ok": not all_llm_failed,
        "reply": reply,
        "summary": summary,
        "findings": [f.to_dict() for f in all_findings],
        "files_reviewed": files_reviewed,
        "file_count": len(payloads),
        "bytes_read": total_bytes,
        "batch_count": batch_count,
        "skill": "zr-workbuddy-code-review",
        "warnings": warnings,
        "local_path": str(root),
        "scope": scope or "",
        "focus": focus or "",
        "source": "code_review",
        "data_source": "code_review",
        "enrich_count": len(seeded),
        "llm_findings_count": llm_count,
        "llm_ok_batches": llm_ok_batches,
        "llm_fail_batches": llm_fail_batches,
        "fresh_id": fresh_id,
        "cache": False,
        "detail": "LLM 全部失败，审查不完整" if all_llm_failed else "",
    }


async def run_llm_review(
    *,
    local_path: str,
    scope: str = "",
    files: list[str] | None = None,
    focus: str = "",
    cfg,
) -> dict[str, Any]:
    """兼容非流式入口。"""
    final: dict[str, Any] = {"ok": False, "detail": "未完成", "reply": "未完成"}
    async for ev in iter_llm_review(
        local_path=local_path,
        scope=scope,
        files=files,
        focus=focus,
        cfg=cfg,
    ):
        if ev.get("type") == "done":
            final = {k: v for k, v in ev.items() if k != "type"}
    return final
