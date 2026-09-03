"""FastAPI 入口：聊天分析 API + 配置 API + 静态页面（SPA）。"""

import json
import os
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 沙箱 DNS 兜底（getaddrinfo 失败时用公共 DNS 解析），必须在任何网络调用前安装
from . import dns_fix

dns_fix.install()

from .config_store import load_config, mask_config, merge_secrets, save_config
from .importers import parse_api_doc, parse_dictionary, parse_swagger
from .nl_engine import llm_chat

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
CHAT_LOG = os.path.join(os.path.dirname(BASE_DIR), "data", "chat_log.jsonl")
_VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "VERSION")


def _app_version() -> str:
    try:
        with open(_VERSION_FILE, encoding="utf-8") as f:
            return (f.read() or "0.0.0").strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def _log_chat(entry: dict):
    """把聊天请求记录到 data/chat_log.jsonl（保留最近 200 条），便于排查意图理解。"""
    try:
        import time as _t
        entry = {"ts": _t.strftime("%Y-%m-%d %H:%M:%S"), **entry}
        lines = []
        if os.path.exists(CHAT_LOG):
            with open(CHAT_LOG, encoding="utf-8") as f:
                lines = f.readlines()
        lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
        with open(CHAT_LOG, "w", encoding="utf-8") as f:
            f.writelines(lines[-200:])
    except Exception:
        pass

app = FastAPI(
    title="ZR-WorkBuddy",
    version=_app_version(),
    description="DSH-ZR-WorkBuddy 业务引擎：工作助手对话、查数出图、配置中心与文档导入；供独立 SPA 与 DSH 客户端面板调用。",
    openapi_tags=[
        {"name": "工作助手", "description": "聊天对话与引擎状态"},
        {"name": "引擎约定", "description": "与 engine_cli 一致的插件调用入口"},
        {"name": "功能热插拔", "description": "features 启停（无需重启 DSH）"},
        {"name": "配置中心", "description": "业务连接 / LLM 配置读写与连接测试"},
        {"name": "文档导入", "description": "接口文档与数据字典导入"},
    ],
)

# CORS：允许本机任意端口的 http Origin（DSH Web / 引擎页常见 3080、动态端口）。
# 引擎默认只绑 127.0.0.1，无自定义鉴权协议（不另造 token）；勿把 host 改成非回环。
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

_LOCAL_ORIGINS = [
    "http://127.0.0.1:3080",
    "http://localhost:3080",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_LOCAL_ORIGINS,
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warn_non_loopback_bind():
    import logging

    from .runtime_conf import read_runtime

    rt = read_runtime()
    host = str(rt.get("host") or "")
    if host not in ("127.0.0.1", "localhost", "::1"):
        logging.getLogger("uvicorn.error").warning(
            "引擎 host=%s 非本机回环：HTTP 接口无鉴权，切勿对公网暴露；请改回 runtime.yaml 的 127.0.0.1",
            host,
        )

from .health import check_net  # noqa: E402


# ================= 聊天分析 =================

class ChatBody(BaseModel):
    message: str
    code_dev_brief: dict | None = None


@app.post(
    "/api/chat",
    tags=["工作助手"],
    summary="自然语言工作助手对话",
    description="聊天页与 DSH 面板共用；与 /api/cli cmd=ask 同一实现（cli_ops.chat）。流式请用 /api/chat/stream。",
)
async def api_chat(body: ChatBody):
    text = (body.message or "").strip()
    if not text:
        return JSONResponse({"ok": False, "detail": "问题不能为空"}, status_code=400)
    from .cli_ops import chat
    out = await chat(text, code_dev_brief=body.code_dev_brief)
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    resp = {
        **out,
        "title": out.get("title") or "",
        "demo": out.get("data_source") == "demo",
        "llm_error": out.get("llm_error") if out.get("source") == "rule" else None,
    }
    _log_chat({
        "question": text,
        "source": resp.get("source"),
        "llm_tried": resp.get("llm_tried"),
        "llm_error": resp.get("llm_error"),
        "intent": resp.get("intent"),
        "data_source": resp.get("data_source"),
    })
    return resp


@app.post(
    "/api/chat/stream",
    tags=["工作助手"],
    summary="流式自然语言对话",
    description="SSE 推送：status / thinking（思考过程）/ reply（正文增量）/ done / error。"
    "写码意图会在 done 中附带 code_dev_ui（选项卡或确认卡）；PCB 问题走专家流式；MES 查数先 status 再一次性 done。",
)
async def api_chat_stream(body: ChatBody):
    import json as _json

    from fastapi.responses import StreamingResponse

    from .cli_ops import chat_stream

    text = (body.message or "").strip()
    if not text:
        return JSONResponse({"ok": False, "detail": "问题不能为空"}, status_code=400)

    async def event_gen():
        try:
            async for ev in chat_stream(text, code_dev_brief=body.code_dev_brief):
                yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev.get("type") == "done":
                    _log_chat({
                        "question": text,
                        "source": ev.get("source"),
                        "data_source": ev.get("data_source"),
                        "intent": ev.get("intent"),
                        "stream": True,
                    })
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'detail': f'{type(e).__name__}: {e}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class CodeDevConfirmBody(BaseModel):
    workspace: str = Field(..., description="本机工程绝对路径")
    requirement: str = Field(..., description="写码需求摘要")
    code_dev_brief: dict | None = Field(None, description="跨轮次写码简报（可选）")
    write_scope: list[str] | None = Field(
        None,
        description="可选：限制同步/优先改动的相对路径（如来自提交门禁 findings）",
    )
    source_gate_job_id: str = Field("", description="可选：来源提交门禁任务 id（cc-…）")


@app.post(
    "/api/code-dev/confirm",
    tags=["本机写码"],
    summary="确认写码并启动本机 Cursor 任务",
    description="用户在聊天确认卡点击后调用；才会真正排队/启动写码 Job。不会自动 commit。"
    "启动后请用 GET /api/code-dev/jobs/{job_id}/stream 订阅进度。",
)
def api_code_dev_confirm(body: CodeDevConfirmBody):
    from . import plugins_store
    from .code_dev.chat_bridge import confirm_and_start
    from .code_dev.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机 Cursor 写码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = confirm_and_start(
        workspace=body.workspace or "",
        requirement=body.requirement or "",
        client_brief=body.code_dev_brief,
        write_scope=body.write_scope,
        source_gate_job_id=body.source_gate_job_id or "",
    )
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    return out


@app.get(
    "/api/code-dev/jobs/{job_id}",
    tags=["本机写码"],
    summary="查询本机写码任务",
    description="返回任务状态、进度步骤、已同步文件与助手小结。",
)
def api_code_dev_job(job_id: str):
    from . import plugins_store
    from .code_dev import get_job as code_dev_get_job
    from .code_dev.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机 Cursor 写码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = code_dev_get_job(job_id)
    if not out.get("ok"):
        return JSONResponse(out, status_code=404)
    return out


@app.get(
    "/api/code-dev/jobs/{job_id}/stream",
    tags=["本机写码"],
    summary="订阅本机写码任务进度（SSE）",
    description="推送 status / step / token / done / error；对齐 simplified local-dev job stream。"
    "已结束的任务会立刻推送终态 done。",
)
async def api_code_dev_job_stream(job_id: str):
    import asyncio
    import json as _json

    from fastapi.responses import StreamingResponse

    from . import plugins_store
    from .code_dev.ops import FEATURE_ID, format_job_done_reply, get_job as code_dev_get_job

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机 Cursor 写码")
    if blocked:
        return JSONResponse(blocked, status_code=400)

    jid = (job_id or "").strip()
    terminal = {"succeeded", "failed", "cancelled"}

    async def event_gen():
        last_n = 0
        last_text_len = 0
        last_progress = ""
        saw_terminal = False
        try:
            for _ in range(3600):  # ~1h @1s
                out = code_dev_get_job(jid)
                if not out.get("ok"):
                    yield f"data: {_json.dumps({'type': 'error', 'message': out.get('detail') or '找不到任务'}, ensure_ascii=False)}\n\n"
                    return
                job = out.get("job") or {}
                st = str(job.get("status") or "")
                events = job.get("events") or []
                for ev in events[last_n:]:
                    if isinstance(ev, dict) and ev.get("type"):
                        yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
                last_n = len(events)

                live = str(job.get("live_text") or "")
                if len(live) > last_text_len:
                    yield f"data: {_json.dumps({'type': 'token', 'text': live[last_text_len:]}, ensure_ascii=False)}\n\n"
                    last_text_len = len(live)

                progress = str(job.get("progress") or "").strip()
                if progress and progress != last_progress and last_n == len(events):
                    # 无新 event 时仍推进度文案
                    yield f"data: {_json.dumps({'type': 'status', 'text': progress}, ensure_ascii=False)}\n\n"
                    last_progress = progress

                if st in terminal:
                    reply = format_job_done_reply(job)
                    yield f"data: {_json.dumps({'type': 'done', 'ok': st == 'succeeded', 'status': st, 'job_id': jid, 'job': job, 'reply': reply, 'synced_files': job.get('synced_files') or [], 'error': job.get('error')}, ensure_ascii=False)}\n\n"
                    saw_terminal = True
                    return
                await asyncio.sleep(1.0)
            if not saw_terminal:
                yield f"data: {_json.dumps({'type': 'error', 'message': '订阅超时，请用 code-dev-job 查询'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'message': f'{type(e).__name__}: {e}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class CodeReviewListBody(BaseModel):
    local_path: str
    scope: str = ""


class CodeReviewRunBody(BaseModel):
    local_path: str
    scope: str = ""
    files: list[str] | None = None
    focus: str = ""


class PickFolderBody(BaseModel):
    prompt: str = "选择工程目录"


@app.post(
    "/api/pick-folder",
    tags=["本机工具"],
    summary="弹出本机选文件夹对话框",
    description="在运行引擎的本机弹出原生文件夹选择框（macOS/Windows/Linux）；"
    "仅适用于浏览器与引擎同机。用于写码/审码确认卡「浏览…」。",
)
def api_pick_folder(body: PickFolderBody = PickFolderBody()):
    from .folder_picker import pick_local_folder

    return pick_local_folder(prompt=(body.prompt or "选择工程目录").strip() or "选择工程目录")


@app.get(
    "/api/code-review/status",
    tags=["本机审码"],
    summary="本机审码就绪状态",
    description="返回审码车道是否开启、LLM 是否可用及读取上限配置。",
)
def api_code_review_status():
    from . import plugins_store
    from .code_review import status as code_review_status
    from .code_review.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机目录审码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    return code_review_status()


@app.post(
    "/api/code-review/check",
    tags=["本机审码"],
    summary="校验本机审码目标路径",
    description="校验绝对路径是否可读、是否为工程目录或支持的源码文件；不涉及 Git。",
)
def api_code_review_check(body: CodeReviewListBody):
    from . import plugins_store
    from .code_review import check_path
    from .code_review.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机目录审码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    return check_path(body.local_path or "")


@app.post(
    "/api/code-review/list",
    tags=["本机审码"],
    summary="列出可审阅的本地源码文件",
    description="直读本机目录，按后缀白名单与敏感路径规则扫描；可选 scope 相对子路径。",
)
def api_code_review_list(body: CodeReviewListBody):
    from . import plugins_store
    from .code_review.ops import FEATURE_ID, list_files as code_review_list_files

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机目录审码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    return code_review_list_files(body.local_path or "", scope=body.scope or "")


@app.post(
    "/api/code-review/run",
    tags=["本机审码"],
    summary="对本机工程执行代码审查",
    description="直读本地文件内容（非 Git diff），经 LLM 输出结构化 findings 与 Markdown 报告；"
    "报告保存于 engine/data/code_review/reports/。确认卡请优先用 /api/code-review/run/stream 看进度。",
)
async def api_code_review_run(body: CodeReviewRunBody):
    from . import plugins_store
    from .code_review.config import availability, get_config
    from .code_review.ops import FEATURE_ID, run_review_async

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机目录审码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    cfg = get_config()
    if not cfg.enabled:
        return JSONResponse(
            {"ok": False, "detail": "本机审码未开启", "reply": "请到配置中心开启审码车道"},
            status_code=400,
        )
    avail = availability()
    if not avail.get("ok"):
        return JSONResponse(
            {"ok": False, "detail": avail.get("detail"), "reply": avail.get("detail")},
            status_code=400,
        )
    out = await run_review_async(
        local_path=body.local_path or "",
        scope=body.scope or "",
        files=body.files,
        focus=body.focus or "",
    )
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    return out


@app.post(
    "/api/code-review/run/stream",
    tags=["本机审码"],
    summary="流式执行本机代码审查（带进度）",
    description="SSE：逐步推送校验/筛选/读码/LLM/汇总；过程中推送草稿 token，终态按行流式推送完整「代码审核汇总报告」。",
)
async def api_code_review_run_stream(body: CodeReviewRunBody):
    import json as _json

    from fastapi.responses import StreamingResponse

    from . import plugins_store
    from .code_review.ops import FEATURE_ID, iter_review_events

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机目录审码")
    if blocked:
        async def err_gen():
            yield f"data: {_json.dumps({**blocked, 'type': 'done', 'ok': False}, ensure_ascii=False)}\n\n"

        return StreamingResponse(err_gen(), media_type="text/event-stream")

    async def event_gen():
        try:
            async for ev in iter_review_events(
                local_path=body.local_path or "",
                scope=body.scope or "",
                files=body.files,
                focus=body.focus or "",
            ):
                yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
                # 促使中间代理/缓冲尽快下发，避免 token 被攒成一包
                if ev.get("type") == "token":
                    yield ": ping\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'done', 'ok': False, 'detail': f'{type(e).__name__}: {e}', 'reply': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get(
    "/api/code-review/reports/{report_id}",
    tags=["本机审码"],
    summary="查询审码报告",
    description="按 report_id（cr- 前缀）读取已保存的审码报告 JSON。",
)
def api_code_review_report(report_id: str):
    from . import plugins_store
    from .code_review import get_report
    from .code_review.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机目录审码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = get_report(report_id)
    if not out.get("ok"):
        return JSONResponse(out, status_code=404)
    return out


class CodeCommitPathBody(BaseModel):
    workspace: str = Field("", description="本机 Git 工程绝对路径")
    files: list[str] | None = Field(None, description="可选：限定待提交相对路径列表")
    work_branch: str = Field(
        "",
        description="要提交的工作分支；空则按「当前分支 → 配置中心 → 需手填」解析",
    )


class CodeCommitConfirmBody(BaseModel):
    job_id: str
    message: str = ""
    push: bool | None = None
    decision: str = "approve"


@app.get(
    "/api/code-commit/status",
    tags=["人触发提交"],
    summary="提交车道就绪状态",
    description="返回提交车道是否开启、默认是否推送、工作分支与远程名等配置。",
)
def api_code_commit_status():
    from . import plugins_store
    from .code_commit import status as code_commit_status
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    return code_commit_status()


@app.post(
    "/api/code-commit/check",
    tags=["人触发提交"],
    summary="校验本机 Git 工程路径",
    description="校验绝对路径是否为可读的 git 仓库目录，并返回提交分支预览"
    "（当前分支 → 配置中心 → 需手填）；不执行 commit。",
)
def api_code_commit_check(body: CodeCommitPathBody):
    from . import plugins_store
    from .code_commit import check_path
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    return check_path(body.workspace or "")


@app.post(
    "/api/code-commit/prepare",
    tags=["人触发提交"],
    summary="列出待提交业务源码",
    description="优先取 Git dirty ∩ 写码同步池，回落为 Git 工作区业务改动；不跑门禁、不 commit。",
)
def api_code_commit_prepare(body: CodeCommitPathBody):
    from . import plugins_store
    from .code_commit import prepare
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    return prepare(body.workspace or "", files=body.files, work_branch=body.work_branch or "")


@app.post(
    "/api/code-commit/start",
    tags=["人触发提交"],
    summary="启动提交门禁审核",
    description="列出待提交文件并跑门禁（P0/P1 阻断）；可传 work_branch。"
    "返回 findings 列表与 job_id。阻断则不可确认；通过后须再调 /api/code-commit/confirm。"
    "不输出全量审码报告。",
)
def api_code_commit_start(body: CodeCommitPathBody):
    from . import plugins_store
    from .code_commit import start_gate
    from .code_commit.config import get_config
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    cfg = get_config()
    if not cfg.enabled:
        return JSONResponse(
            {"ok": False, "detail": "提交车道未开启", "reply": "请到配置中心开启提交车道", "can_commit": False},
            status_code=400,
        )
    out = start_gate(
        body.workspace or "",
        files=body.files,
        work_branch=body.work_branch or "",
    )
    if not out.get("ok") and not out.get("job_id"):
        return JSONResponse(out, status_code=400)
    return out


@app.post(
    "/api/code-commit/confirm",
    tags=["人触发提交"],
    summary="人确认后执行 git commit/push",
    description="仅 HITL：用户在确认卡点确认后调用；才会在工作分支 commit，并可 push。"
    "decision=reject 则跳过。模型不得代调本接口完成提交。",
)
def api_code_commit_confirm(body: CodeCommitConfirmBody):
    from . import plugins_store
    from .code_commit import confirm
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = confirm(
        body.job_id or "",
        message=body.message or "",
        push=body.push,
        decision=body.decision or "approve",
    )
    if not out.get("ok"):
        # 本地已 commit、仅 push 失败：200 + push_retry_needed，供 UI 出「重试推送」
        if out.get("push_retry_needed"):
            return JSONResponse(out, status_code=200)
        return JSONResponse(out, status_code=400)
    return out


@app.get(
    "/api/code-commit/jobs/{job_id}",
    tags=["人触发提交"],
    summary="查询提交任务",
    description="按 job_id（cc- 前缀）读取门禁结果、文件列表与 commit 结果。",
)
def api_code_commit_job(job_id: str):
    from . import plugins_store
    from .code_commit import get_job
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = get_job(job_id)
    if not out.get("ok"):
        return JSONResponse(out, status_code=404)
    return out


class CodeCommitFixBody(BaseModel):
    workspace: str = Field("", description="可选：限定工程路径，默认取最近阻断任务")
    job_id: str = Field("", description="可选：指定门禁任务 id（cc-…）")


@app.post(
    "/api/code-commit/pick-ui",
    tags=["人触发提交"],
    summary="生成提交选目录确认卡",
    description="按工程路径返回 code_commit_ui（pick），用于写码修复成功后继续提交闭环；不跑门禁、不 commit。",
)
def api_code_commit_pick_ui(body: CodeCommitFixBody):
    from . import plugins_store
    from .code_commit.chat_bridge import build_pick_ui
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    ui = build_pick_ui(workspace=body.workspace or "")
    return {
        "ok": True,
        "code_commit_ui": ui,
        "reply": "请确认工程目录与提交分支后开始门禁审核。",
        "detail": ui.get("workspace") or "",
    }


@app.post(
    "/api/code-commit/latest-blocked",
    tags=["人触发提交"],
    summary="查询最近一次阻断门禁",
    description="返回最近 status=blocked 的提交任务及 findings 路径，供「修复这些问题」闭环使用。",
)
def api_code_commit_latest_blocked(body: CodeCommitFixBody):
    from . import plugins_store
    from .code_commit import latest_blocked
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = latest_blocked(workspace=body.workspace or "", job_id=body.job_id or "")
    if not out.get("ok"):
        return JSONResponse(out, status_code=404)
    return out


@app.post(
    "/api/code-commit/prepare-fix",
    tags=["人触发提交"],
    summary="按门禁阻断生成写码确认卡",
    description="读取最近（或指定）阻断任务，生成 code_dev_ui 确认卡数据；不自动启动 Cursor。"
    "用户确认后走 POST /api/code-dev/confirm。",
)
def api_code_commit_prepare_fix(body: CodeCommitFixBody):
    from . import plugins_store
    from .code_commit import prepare_fix_from_gate
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = prepare_fix_from_gate(workspace=body.workspace or "", job_id=body.job_id or "")
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    return out


@app.post(
    "/api/code-commit/push-retry",
    tags=["人触发提交"],
    summary="重试推送（不重新 commit）",
    description="本地已 commit 但 push 失败时，仅重试推送到远程。",
)
def api_code_commit_push_retry(body: CodeCommitConfirmBody):
    from . import plugins_store
    from .code_commit import push_retry
    from .code_commit.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = push_retry(body.job_id or "")
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    return out


class CodeDeployPrepareBody(BaseModel):
    workspace: str = Field("", description="本机 Git 仓库根；空则用配置 default_workspace")
    env: str = Field("", description="环境名，默认 staging")
    base_ref: str = Field("", description="对比基线；空则上次成功部署 SHA 或 HEAD~1")
    head_ref: str = Field("HEAD", description="对比终点，默认 HEAD")
    mode: str = Field(
        "auto",
        description="auto|full|incremental；auto=无上次部署记录则全量，否则增量",
    )
    unit_ids: list[str] | None = Field(
        None,
        description="强制指定单元，如 feature:code-commit、feature:code-dev、engine、bridge",
    )


class CodeDeployConfirmBody(BaseModel):
    job_id: str = Field(..., description="prepare 返回的 job_id")
    decision: str = Field("approve", description="approve|reject")
    mode: str = Field(
        "",
        description="full|incremental；空则用 prepare 时默认（首次多为 full）",
    )
    unit_ids: list[str] | None = Field(
        None,
        description="确认时勾选的单元；全量且不传则同步全部目录单元",
    )


@app.get(
    "/api/code-deploy/status",
    tags=["按插件增量部署"],
    summary="部署车道就绪状态",
    description="返回部署开关、环境白名单、SSH 是否配齐等；不执行同步。",
)
def api_code_deploy_status():
    from . import plugins_store
    from .code_deploy import status as code_deploy_status
    from .code_deploy.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="按插件增量部署")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    return code_deploy_status()


@app.post(
    "/api/code-deploy/prepare",
    tags=["按插件增量部署"],
    summary="准备全量或增量部署确认卡",
    description="零副作用：首次默认全量（全部插件+引擎/bridge）；增量按 git diff 映射单元。"
    "不执行 rsync。",
)
def api_code_deploy_prepare(body: CodeDeployPrepareBody):
    from . import plugins_store
    from .code_deploy import prepare
    from .code_deploy.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="按插件增量部署")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = prepare(
        body.workspace or "",
        env=body.env or "",
        base_ref=body.base_ref or "",
        head_ref=body.head_ref or "HEAD",
        unit_ids=body.unit_ids,
        mode=body.mode or "auto",
    )
    if not out.get("ok") and not out.get("job_id"):
        return JSONResponse(out, status_code=400)
    return out


@app.post(
    "/api/code-deploy/confirm",
    tags=["按插件增量部署"],
    summary="人确认后全量或按勾选单元 SSH/rsync",
    description="仅 HITL：mode=full 同步目录全量单元；mode=incremental 仅同步勾选单元。"
    "模型不得代调本接口完成部署。",
)
def api_code_deploy_confirm(body: CodeDeployConfirmBody):
    from . import plugins_store
    from .code_deploy import confirm
    from .code_deploy.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="按插件增量部署")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = confirm(
        body.job_id or "",
        decision=body.decision or "approve",
        unit_ids=body.unit_ids,
        mode=(body.mode or None),
    )
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    return out


@app.get(
    "/api/code-deploy/jobs/{job_id}",
    tags=["按插件增量部署"],
    summary="查询部署任务",
    description="按 job_id 读取部署任务状态与结果。",
)
def api_code_deploy_job(job_id: str):
    from . import plugins_store
    from .code_deploy import get_job
    from .code_deploy.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="按插件增量部署")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = get_job(job_id)
    if not out.get("ok"):
        return JSONResponse(out, status_code=404)
    return out


def _read_runtime_yaml() -> dict:
    from .runtime_conf import read_runtime
    return read_runtime()


@app.get(
    "/api/runtime",
    tags=["引擎约定"],
    summary="读取运行时地址",
    description="返回 runtime.yaml 中的 host/port（解析实现见 scripts/lib/read_runtime.py）。",
)
def api_runtime():
    rt = _read_runtime_yaml()
    return {"ok": True, **rt}


class CliBody(BaseModel):
    cmd: str
    args: List[str] = []


@app.post(
    "/api/cli",
    tags=["引擎约定"],
    summary="插件统一调用入口",
    description="与 engine_cli.py 命令一致：ask / pcb-ask / status / config-test-* / plugins-*。",
)
async def api_cli(body: CliBody):
    from .cli_ops import run_async
    cmd = (body.cmd or "").strip()
    if not cmd:
        return JSONResponse({"ok": False, "detail": "cmd 不能为空"}, status_code=400)
    try:
        out = await run_async(cmd, list(body.args or []))
    except Exception as e:
        out = {"ok": False, "detail": f"{type(e).__name__}: {e}"}
    return out


class PluginBody(BaseModel):
    id: str = ""


@app.get(
    "/api/plugins",
    tags=["功能热插拔"],
    summary="功能插件列表与启停状态",
    description="自动扫描 features/（含 index.js 的目录），无白名单；新增 feature 即出现在列表。"
    "不含 mes-bridge / mes-runtime。供引擎 SPA「功能插件」页与 bridge 热插拔；真相源 data/plugins.json。",
)
def api_plugins_list():
    from . import plugins_store
    return plugins_store.snapshot()


@app.post(
    "/api/plugins/enable",
    tags=["功能热插拔"],
    summary="启用功能插件",
    description="写入 plugins.json；mes-bridge 约 1.5s 内 ctx.plugin 加载，无需重启 DSH。",
)
def api_plugins_enable(body: PluginBody):
    from . import plugins_store
    return plugins_store.enable(body.id)


@app.post(
    "/api/plugins/disable",
    tags=["功能热插拔"],
    summary="停用功能插件",
    description="写入 plugins.json；mes-bridge dispose fiber，工具立即消失。",
)
def api_plugins_disable(body: PluginBody):
    from . import plugins_store
    return plugins_store.disable(body.id)


@app.get(
    "/api/status",
    tags=["工作助手"],
    summary="引擎与连接状态",
    description="与 /api/cli cmd=status 同源（status_info.build_status）；HTTP 额外含演示数据规模。",
)
def api_status():
    from .status_info import build_status

    return build_status(include_demo=True)


# ================= 配置中心 =================

class ConfigBody(BaseModel):
    config: Dict[str, Any]


@app.get(
    "/api/config",
    tags=["配置中心"],
    summary="读取配置",
    description="返回运行时配置；密码与 API Key 已脱敏。",
)
def api_get_config():
    return {"ok": True, "config": mask_config(load_config())}


@app.put(
    "/api/config",
    tags=["配置中心"],
    summary="保存配置",
    description="合并写入 config.yaml；脱敏占位符不覆盖原密钥。",
)
def api_put_config(body: ConfigBody):
    merged = merge_secrets(load_config(), body.config)
    save_config(merged)
    return {"ok": True, "config": mask_config(merged)}


@app.post(
    "/api/config/test/mes",
    tags=["配置中心"],
    summary="测试 MES 连接",
    description="与 CLI config-test-mes 同一实现（mes_client.probe_connection）。",
)
async def api_test_mes(body: ConfigBody):
    from .mes_client import probe_connection

    saved = load_config()
    mes = merge_secrets(saved, body.config)["mes"]
    out = await probe_connection(mes)
    if not out.get("ok") and "base_url 为空" in str(out.get("detail") or ""):
        return JSONResponse({"ok": False, "detail": "请先填写 MES 访问地址"}, status_code=400)
    return out


@app.post(
    "/api/config/test/deepseek",
    tags=["配置中心"],
    summary="测试 LLM 连接",
    description="按 provider 测试 DeepSeek API Key 或本机 Ollama 模型是否可用。",
)
async def api_test_deepseek(body: ConfigBody):
    saved = load_config()
    llm = merge_secrets(saved, body.config)["deepseek"]
    provider = (llm.get("provider") or "deepseek").lower()

    if provider == "ollama":
        base = (llm.get("base_url") or "http://127.0.0.1:11434").strip().rstrip("/")
        model = (llm.get("model") or "").strip()
        if not model:
            return JSONResponse({"ok": False, "detail": "请填写 Ollama 模型名（如 qwen2.5:7b）"}, status_code=400)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(base + "/api/tags")
                if r.status_code != 200:
                    return {"ok": False, "detail": f"Ollama 服务不可达（HTTP {r.status_code}）"}
                names = [m.get("name", "") for m in (r.json().get("models") or [])]
                if model in names:
                    return {"ok": True, "detail": f"Ollama 连接成功，模型 {model} 已就绪（本机模型列表：{'、'.join(names[:6]) or '空'}）"}
                return {"ok": False, "detail": f"Ollama 连接成功，但未找到模型「{model}」。本机已有：{('、'.join(names) or '无，请先 ollama pull 模型')}"}
        except Exception as e:
            return {"ok": False, "detail": f"Ollama 连接失败：{type(e).__name__}: {e}"}

    # deepseek（OpenAI 兼容）
    key = (llm.get("api_key") or "").strip()
    if not key:
        return JSONResponse({"ok": False, "detail": "请先填写 DeepSeek API Key"}, status_code=400)
    if not check_net():
        return {"ok": False, "detail": "当前环境无外网（DeepSeek 接口不可达），Key 已保存，网络恢复后自动生效"}

    base = (llm.get("base_url") or "https://api.deepseek.com").strip().rstrip("/")
    model = llm.get("model") or "deepseek-chat"
    v1 = base if base.endswith("/v1") else base + "/v1"
    headers = {"Authorization": f"Bearer {key}"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(v1 + "/models", headers=headers)
            if r.status_code == 200:
                return {"ok": True, "detail": "Key 有效（可访问模型列表）"}
            r2 = await client.post(
                v1 + "/chat/completions",
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
            )
            if r2.status_code == 200:
                return {"ok": True, "detail": f"Key 有效（chat 接口测试通过，模型 {model}）"}
            return {"ok": False, "detail": f"Key 无效或接口错误（HTTP {r2.status_code}）：{r2.text[:300]}"}
    except Exception as e:
        return {"ok": False, "detail": f"连接失败：{type(e).__name__}: {e}"}


# ================= 文档导入（Swagger / 数据字典） =================

class ImportTextBody(BaseModel):
    content: str
    filename: str = ""


async def _read_upload(file) -> bytes:
    return await file.read()


@app.post(
    "/api/config/import/swagger",
    tags=["文档导入"],
    summary="上传接口文档解析",
    description="上传 OpenAPI/Swagger 或 Markdown 接口文档，解析为 endpoints 预览。",
)
async def api_import_swagger(file: UploadFile):
    try:
        content = (await _read_upload(file)).decode("utf-8")
        result = parse_api_doc(file.filename or "", content)
        return {"ok": True, **result}
    except ValueError as e:
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=400)
    except UnicodeDecodeError:
        return JSONResponse({"ok": False, "detail": "文件编码不是 UTF-8，请另存为 UTF-8 后重试"}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "detail": f"解析失败：{type(e).__name__}: {e}"}, status_code=400)


@app.post(
    "/api/config/import/swagger/text",
    tags=["文档导入"],
    summary="粘贴接口文档解析",
    description="粘贴 OpenAPI/Markdown 原文并解析为 endpoints 预览。",
)
async def api_import_swagger_text(body: ImportTextBody):
    try:
        result = parse_api_doc("", body.content)
        return {"ok": True, **result}
    except ValueError as e:
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "detail": f"解析失败：{type(e).__name__}: {e}"}, status_code=400)


@app.post(
    "/api/config/import/dictionary",
    tags=["文档导入"],
    summary="上传数据字典解析",
    description="上传 xlsx/csv/txt/docx/md，解析字段并建议标准字段名。",
)
async def api_import_dictionary(file: UploadFile):
    filename = file.filename or "dict"
    try:
        data = await _read_upload(file)
        result = parse_dictionary(filename, data)
        return {"ok": True, **result}
    except ValueError as e:
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "detail": f"解析失败：{type(e).__name__}: {e}"}, status_code=400)


@app.post(
    "/api/config/import/dictionary/text",
    tags=["文档导入"],
    summary="粘贴数据字典解析",
    description="粘贴数据字典原文并解析归类。",
)
async def api_import_dictionary_text(body: ImportTextBody):
    try:
        result = parse_dictionary(body.filename or "dict.txt", body.content.encode("utf-8"))
        return {"ok": True, **result}
    except ValueError as e:
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "detail": f"解析失败：{type(e).__name__}: {e}"}, status_code=400)


# ---------- 接口文档 URL 导入 ----------

class SwaggerUrlBody(BaseModel):
    url: str
    username: str = ""
    password: str = ""


def _openapi_candidates(url: str) -> list:
    """HTML 文档页（/docs /swagger 等）→ 常见 OpenAPI JSON 路径候选。"""
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    for suffix in ("/docs", "/redoc", "/swagger-ui", "/swagger-ui.html", "/swagger",
                   "/index.html", "/api-docs", "/v2/api-docs"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    base = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    return [base + "/openapi.json", base + "/swagger.json", base + "/v2/api-docs", base + "/api-docs"]


def _swagger_url_allowed(url: str) -> str | None:
    """拒绝明显危险目标（云元数据 / 非 http(s)）；厂内 MES OpenAPI 仍允许内网 IP。"""
    from urllib.parse import urlparse
    import ipaddress
    import socket

    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        return "仅允许 http/https"
    host = (parts.hostname or "").strip().lower()
    if not host:
        return "URL 缺少主机名"
    blocked_names = {"metadata.google.internal", "metadata.goog", "instance-data"}
    if host in blocked_names or host.endswith(".metadata.google.internal"):
        return "拒绝访问云元数据主机"
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if addr.is_link_local or str(addr) == "169.254.169.254":
                return "拒绝访问链路本地/元数据地址"
    except socket.gaierror:
        pass
    return None


async def _fetch_openapi(url: str, username: str = "", password: str = "") -> tuple:
    """抓取并返回 (openapi 文本, 实际来源 URL)。自动处理 /docs 等 HTML 页面。"""
    bad = _swagger_url_allowed(url)
    if bad:
        raise ValueError(bad)
    auth = (username, password) if username else None
    # SSL 校验跟随已保存 MES 配置；默认 verify=True（不再无条件 verify=False）
    mes = (load_config().get("mes") or {})
    verify = bool(mes.get("verify_ssl", True))
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=verify) as client:
        r = await client.get(url, auth=auth)
        r.raise_for_status()
        # 重定向后再次校验最终 URL
        final = str(r.url)
        bad2 = _swagger_url_allowed(final)
        if bad2:
            raise ValueError(bad2)
        content = r.text
        try:
            parse_swagger(content)
            return content, final
        except Exception:
            pass
        for cand in _openapi_candidates(final):
            try:
                rr = await client.get(cand, auth=auth)
                if rr.status_code == 200:
                    parse_swagger(rr.text)
                    return rr.text, cand
            except Exception:
                continue
    raise ValueError(f"无法从 {url} 获取 OpenAPI 文档（已尝试 /openapi.json、/swagger.json、/v2/api-docs 等）")


@app.post(
    "/api/config/import/swagger/url",
    tags=["文档导入"],
    summary="从 URL 拉取接口文档",
    description="填写文档 URL（如 /docs），自动转 openapi.json 等候选并解析。",
)
async def api_import_swagger_url(body: SwaggerUrlBody):
    url = (body.url or "").strip()
    if not url:
        return JSONResponse({"ok": False, "detail": "请填写接口文档 URL"}, status_code=400)
    if not url.startswith(("http://", "https://")):
        return JSONResponse({"ok": False, "detail": "URL 需以 http:// 或 https:// 开头"}, status_code=400)
    try:
        content, src = await _fetch_openapi(url, body.username, body.password)
    except httpx.HTTPError as e:
        return JSONResponse({"ok": False, "detail": f"获取失败：{type(e).__name__}: {e}"}, status_code=400)
    except ValueError as e:
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "detail": f"获取失败：{type(e).__name__}: {e}"}, status_code=400)
    try:
        result = parse_api_doc("url", content)
        return {"ok": True, **result, "source_url": src}
    except ValueError as e:
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=400)


# ---------- 导入即保存（确认导入后直接写入配置） ----------

class SwaggerCommitBody(BaseModel):
    endpoints: List[Dict[str, Any]]


@app.post(
    "/api/config/import/swagger/commit",
    tags=["文档导入"],
    summary="确认写入接口清单",
    description="将预览的 endpoints 写入 config.yaml 的 api_docs。",
)
def api_commit_swagger(body: SwaggerCommitBody):
    if not isinstance(body.endpoints, list):
        return JSONResponse({"ok": False, "detail": "endpoints 必须是数组"}, status_code=400)
    cfg = load_config()
    cfg["api_docs"]["endpoints"] = body.endpoints
    save_config(cfg)
    return {"ok": True, "count": len(body.endpoints)}


class DictCommitBody(BaseModel):
    groups: Dict[str, List[Dict[str, Any]]]


@app.post(
    "/api/config/import/dictionary/commit",
    tags=["文档导入"],
    summary="确认写入数据字典",
    description="将预览的字段分组写入 config.yaml 的 data_dictionary。",
)
def api_commit_dictionary(body: DictCommitBody):
    cfg = load_config()
    dd = cfg.setdefault("data_dictionary", {})
    groups = body.groups or {}
    for k in ("work_orders", "equipment_events", "quality_records"):
        rows = list(groups.get(k) or [])
        if k == "work_orders":  # 未分类字段并入生产工单表
            rows += list(groups.get("uncategorized") or [])
        seen, dedup = set(), []
        for r in rows:
            f = (r.get("mes_field") or "").strip()
            if f and f not in seen:
                seen.add(f)
                dedup.append({"mes_field": f,
                              "std_field": (r.get("std_field") or "").strip(),
                              "type": (r.get("type") or "文本").strip() or "文本",
                              "desc": (r.get("desc") or "").strip()})
        dd[k] = dedup
    save_config(cfg)
    return {"ok": True,
            "counts": {k: len(dd[k]) for k in ("work_orders", "equipment_events", "quality_records")},
            "total": sum(len(dd[k]) for k in ("work_orders", "equipment_events", "quality_records"))}


# ================= 静态页面 =================

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(
        os.path.join(STATIC_DIR, "index.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
