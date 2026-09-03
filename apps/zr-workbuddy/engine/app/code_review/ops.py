"""审码命令面：CLI / HTTP / feature 同源。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .config import availability, get_config
from .local_files import list_review_files, select_files_for_review
from .review import iter_llm_review
from .store import load_report, save_report
from .workspace import resolve_scope_root, validate_review_root

FEATURE_ID = "code-review"


def default_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


async def iter_review_events(
    *,
    local_path: str,
    scope: str = "",
    files: list[str] | None = None,
    focus: str = "",
    persist: bool = True,
):
    """SSE 用：逐步 yield step/status，最后 done（含 report_id）。"""
    cfg = get_config()
    if not cfg.enabled:
        yield {
            "type": "done",
            "ok": False,
            "detail": "本机审码未开启：请到引擎「配置中心 → 审码车道」勾选开启并保存",
            "reply": "本机审码未开启",
        }
        return
    avail = availability()
    if not avail.get("ok"):
        yield {
            "type": "done",
            "ok": False,
            "detail": avail.get("detail") or "审码未就绪",
            "reply": avail.get("detail") or "审码未就绪",
        }
        return

    async for ev in iter_llm_review(
        local_path=local_path,
        scope=scope,
        files=files,
        focus=focus,
        cfg=cfg,
    ):
        if ev.get("type") != "done":
            yield ev
            continue

        if ev.get("ok") and persist:
            report = save_report(
                default_data_dir(),
                {**{k: v for k, v in ev.items() if k != "type"}, "feature": FEATURE_ID},
            )
            rid = report.get("id")
            ev = {
                **ev,
                "report_id": rid,
                "reply": (ev.get("reply") or "") + (f"\n\n报告 ID：`{rid}`" if rid else ""),
            }

        # 终稿按「一行」SSE 推送；前端再排队逐行渲染，避免同帧刷完看起来像整段弹出
        reply = ev.get("reply") or ""
        if ev.get("ok") and reply.strip():
            yield {"type": "status", "detail": "正在逐行流式输出审核报告…"}
            acc = ""
            for line in reply.splitlines(keepends=True):
                acc += line
                yield {"type": "token", "text": acc, "delta": line}
                # 给浏览器时间拆包渲染（过短会被合成一帧）
                await asyncio.sleep(0.045)
            if acc != reply:
                yield {"type": "token", "text": reply, "delta": ""}

        yield ev


async def run_review_async(
    *,
    local_path: str,
    scope: str = "",
    files: list[str] | None = None,
    focus: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    final: dict[str, Any] = {"ok": False, "detail": "未完成", "reply": "未完成"}
    async for ev in iter_review_events(
        local_path=local_path,
        scope=scope,
        files=files,
        focus=focus,
        persist=persist,
    ):
        if ev.get("type") == "done":
            final = {k: v for k, v in ev.items() if k != "type"}
    return final


def status() -> dict[str, Any]:
    avail = availability()
    cfg = get_config()
    return {
        "ok": True,
        "feature": FEATURE_ID,
        "code_review": avail,
        "max_files": cfg.max_files,
        "max_file_bytes": cfg.max_file_bytes,
        "max_total_bytes": cfg.max_total_bytes,
        "reply": avail.get("detail") or "",
        "detail": avail.get("detail") or "",
    }


def check_path(path: str) -> dict[str, Any]:
    out = validate_review_root(path)
    out["ok"] = bool(out.get("ok"))
    if out["ok"]:
        out["detail"] = f"路径可用：{out.get('path')}"
        out["reply"] = out["detail"]
    else:
        out["detail"] = out.get("error") or "路径不可用"
        out["reply"] = out["detail"]
    return out


def list_files(
    path: str,
    *,
    scope: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    check = validate_review_root(path)
    if not check.get("ok"):
        return {"ok": False, "detail": check.get("error"), "reply": check.get("error")}

    root = Path(check["path"])
    if check.get("is_file"):
        return {
            "ok": True,
            "local_path": str(root.parent),
            "files": [{"path": root.name, "bytes": root.stat().st_size if root.exists() else 0}],
            "count": 1,
            "reply": f"单文件：{root.name}",
            "detail": "单文件模式",
        }

    scope_root, scope_err = resolve_scope_root(root, scope)
    if scope_err:
        return {"ok": False, "detail": scope_err, "reply": scope_err}

    files = list_review_files(root, scope_root=scope_root, limit=min(limit, 500))
    cfg = get_config()
    selected, warnings = select_files_for_review(
        root,
        scope_root=scope_root,
        explicit_files=None,
        cfg=cfg,
    )
    return {
        "ok": True,
        "local_path": str(root),
        "scope": scope or "",
        "files": files,
        "count": len(files),
        "sample_selected": selected,
        "warnings": warnings,
        "reply": f"共 {len(files)} 个可审阅文件（展示上限 {limit}）",
        "detail": f"默认审码将优先取 {len(selected)} 个文件",
    }


def _parse_files_arg(raw: str) -> list[str] | None:
    text = (raw or "").strip()
    if not text:
        return None
    parts = [p.strip().replace("\\", "/") for p in text.replace(",", "\n").splitlines()]
    return [p for p in parts if p] or None


def run_review(
    *,
    local_path: str,
    scope: str = "",
    files: list[str] | None = None,
    focus: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    """同步入口（CLI）；HTTP 请用 run_review_async。"""
    return asyncio.run(
        run_review_async(
            local_path=local_path,
            scope=scope,
            files=files,
            focus=focus,
            persist=persist,
        )
    )


def get_report(report_id: str) -> dict[str, Any]:
    row = load_report(default_data_dir(), report_id)
    if not row:
        return {"ok": False, "detail": "报告不存在", "reply": "报告不存在"}
    return {"ok": True, "report": row, "reply": row.get("reply") or "", "detail": report_id}
