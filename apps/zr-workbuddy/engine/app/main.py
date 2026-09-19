"""FastAPI 入口：聊天分析 API + 配置 API + 静态页面（SPA）。"""

from . import blas_env  # noqa: F401 — 进程尽早设 BLAS 环境，再加载其它依赖

import json
import os
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, File, Form, Query, Request, UploadFile
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
        {"name": "用量统计", "description": "本机 LLM 与 Cursor 写码 token 流水与汇总（只读）"},
        {"name": "资料库", "description": "本机会话摘要与报告档案；按会话列出文档；可预览/下载/删除与保留清理；不当聊天续聊权威"},
        {"name": "账号", "description": "本机登录会话；引擎 SPA 进应用须先登录；用量流水带 user_id"},
        {"name": "文档导入", "description": "接口文档与数据字典导入"},
    ],
)

# CORS：允许本机任意端口的 http Origin（开发壳 :3081 / 桌面 :13080 / 引擎页等）。
# 引擎默认只绑 127.0.0.1，无自定义鉴权协议（不另造 token）；勿把 host 改成非回环。
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

_LOCAL_ORIGINS = [
    "http://127.0.0.1:3081",
    "http://localhost:3081",
    "http://127.0.0.1:3080",
    "http://localhost:3080",
    "http://127.0.0.1:13080",
    "http://localhost:13080",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
app.add_middleware(
    CORSMiddleware,
    # 企业默认：仅固定本机白名单端口，禁止任意 127.0.0.1:* Origin 读取引擎
    allow_origins=_LOCAL_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _hitl_origin_guard(request, call_next):
    """变异接口：若带 Origin/Referer 则必须为本机回环（无头视为 CLI，仍须 HITL nonce）。"""
    from fastapi.responses import JSONResponse

    from .hitl import local_origin_ok, mutating_path_guarded

    if mutating_path_guarded(request.url.path, request.method):
        bad = local_origin_ok(
            request.headers.get("origin"),
            request.headers.get("referer"),
        )
        if bad:
            return JSONResponse({"ok": False, "detail": bad, "code": "origin_rejected"}, status_code=403)
    return await call_next(request)


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
    try:
        from .auth import ensure_seed_users

        ensure_seed_users()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("uvicorn.error").warning("本机账号种子初始化失败：%s", exc)
    try:
        from .usage import backfill_orphan_user_id

        n = backfill_orphan_user_id()
        if n:
            logging.getLogger("uvicorn.error").info("用量：已将 %d 条历史引擎流水归到本机账号", n)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("uvicorn.error").warning("用量历史流水归户失败：%s", exc)
    try:
        from .code_dev.service import default_data_dir, reconcile_stale_jobs

        n = reconcile_stale_jobs(default_data_dir())
        if n:
            logging.getLogger("uvicorn.error").info("本机写码：已将 %d 个孤儿任务标为已取消", n)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("uvicorn.error").warning("本机写码孤儿任务 reconcile 失败：%s", exc)

    def _delayed_usage_report() -> None:
        import time

        time.sleep(3)
        try:
            from .usage.report import flush_report

            flush_report(force=True)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("uvicorn.error").warning("用量上报启动刷新失败：%s", exc)

    try:
        import threading

        threading.Thread(target=_delayed_usage_report, name="usage-report", daemon=True).start()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("uvicorn.error").warning("用量上报后台线程启动失败：%s", exc)

    def _delayed_space_purge() -> None:
        import time

        time.sleep(5)
        try:
            from .space import get_space_config, purge_expired

            cfg = get_space_config()
            if not cfg.get("auto_purge_enabled"):
                return
            out = purge_expired(dry_run=False)
            n = int((out or {}).get("purged_sessions") or 0)
            if n:
                logging.getLogger("uvicorn.error").info("我的空间：已清理 %d 个过期会话档案", n)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("uvicorn.error").warning("我的空间启动清理失败：%s", exc)

    try:
        import threading

        threading.Thread(target=_delayed_space_purge, name="space-purge", daemon=True).start()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("uvicorn.error").warning("我的空间清理线程启动失败：%s", exc)

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
    nonce: str = Field(
        "",
        description="确认卡签发的一次性 HITL nonce（POST /api/hitl/issue）；无 nonce 拒绝开工",
    )
    ui_call_id: str = Field(
        "",
        description="DSH 工具卡 callId：绑定 Job，刷新后按 callId 恢复进度卡",
    )
    ui_session_id: str = Field("", description="DSH 会话 sessionId（可选）")


class HitlIssueBody(BaseModel):
    action: str = Field(
        ...,
        description="仅 code-dev.confirm | code-commit.confirm | code-deploy.confirm（path_ticket 不经本接口）",
    )
    workspace: str = Field("", description="写码绑定工程路径")
    job_id: str = Field("", description="提交/部署绑定 job_id")
    path: str = Field("", description="（已废弃）path_ticket 请走列文件/校验，勿经本接口")
    requirement: str = Field("", description="写码确认时绑定的需求摘要（用于 nonce 防篡改）")
    payload_hash: str = Field("", description="可选：需求摘要 sha256 前 32 位；与 requirement 二选一")


class CodeDevDiscussBody(BaseModel):
    message: str = Field(..., description="用户原文，或「【写码需求选项已确认】」勾选结果")
    workspace: str = Field("", description="本机工程绝对路径（可选；并入讨论上下文）")
    code_dev_brief: dict | None = Field(None, description="跨轮次写码简报（选项确认时必带回）")


@app.post(
    "/api/hitl/issue",
    tags=["人机确认"],
    summary="签发 HITL 一次性票据",
    description="仅确认卡 UI 在用户点击前调用（须 X-WorkBuddy-Hitl: ui + 本机 Origin）。"
    "可签发 code-dev/commit/deploy.confirm；path_ticket 不经本接口（仅列文件/校验后附带）。"
    "Agent/脚本不得签发。",
)
def api_hitl_issue(body: HitlIssueBody, request: Request):
    from .hitl import HTTP_ISSUE_ACTIONS, issue, issue_surface_ok

    surface = issue_surface_ok(
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        ui_header=request.headers.get("x-workbuddy-hitl"),
    )
    if surface:
        return JSONResponse(
            {"ok": False, "detail": surface, "code": "hitl_issue_forbidden"},
            status_code=403,
        )
    act = (body.action or "").strip()
    if act not in HTTP_ISSUE_ACTIONS:
        return JSONResponse(
            {
                "ok": False,
                "detail": "该 action 不可经 HTTP 签发（path_ticket 请走列文件/校验）",
                "code": "hitl_action_not_http",
            },
            status_code=400,
        )
    from .hitl import ACTION_DEV
    from .hitl.tokens import normalize_payload_hash

    req = (body.requirement or "").strip()
    ph = (body.payload_hash or "").strip().lower()
    # 写码确认：必须带 requirement，hash 一律由服务端从正文计算，防 UI 展示与绑定脱节
    if act == ACTION_DEV:
        if not req:
            return JSONResponse(
                {
                    "ok": False,
                    "detail": "写码确认签发须带 requirement（与确认卡正文一致）",
                    "code": "hitl_requirement_missing",
                },
                status_code=400,
            )
        computed = normalize_payload_hash(req)
        if ph and ph != computed:
            return JSONResponse(
                {
                    "ok": False,
                    "detail": "requirement 与 payload_hash 不一致",
                    "code": "hitl_payload_mismatch",
                },
                status_code=400,
            )
        ph = computed
    elif not ph and req:
        ph = normalize_payload_hash(req)
    out = issue(
        action=act,
        workspace=body.workspace or "",
        job_id=body.job_id or "",
        path=body.path or "",
        payload_hash=ph,
    )
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    return out


@app.post(
    "/api/code-dev/discuss",
    tags=["本机写码"],
    summary="写码需求讨论（选项卡/确认卡）",
    description="对齐引擎聊天写码 HITL：梳理需求并返回 code_dev_ui（options 或 propose），"
    "绝不在此启动 Cursor Job。确认开工请用 POST /api/code-dev/confirm。",
)
async def api_code_dev_discuss(body: CodeDevDiscussBody):
    from . import plugins_store
    from .code_dev.chat_bridge import handle_chat_code_dev
    from .code_dev.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机 Cursor 写码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    raw = (body.message or "").strip()
    if not raw:
        return JSONResponse({"ok": False, "detail": "message 不能为空"}, status_code=400)
    ws = (body.workspace or "").strip()
    text = raw
    if ws and ws not in raw and not raw.startswith("【写码需求选项已确认】"):
        text = f"在 {ws} 开发：{raw}"
    return await handle_chat_code_dev(text, client_brief=body.code_dev_brief)


@app.post(
    "/api/code-dev/confirm",
    tags=["本机写码"],
    summary="确认写码并启动本机 Cursor 任务",
    description="用户在聊天确认卡点击后调用；须带 HITL nonce。"
    "才会真正排队/启动写码 Job。不会自动 commit。"
    "启动后请用 GET /api/code-dev/jobs/{job_id}/stream 订阅进度。",
)
def api_code_dev_confirm(body: CodeDevConfirmBody):
    from . import plugins_store
    from .code_dev.chat_bridge import confirm_and_start
    from .code_dev.ops import FEATURE_ID
    from .hitl import ACTION_DEV, require_confirm_nonce

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机 Cursor 写码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    from .hitl.tokens import normalize_payload_hash

    gate = require_confirm_nonce(
        nonce=body.nonce or "",
        action=ACTION_DEV,
        workspace=body.workspace or "",
        payload_hash=normalize_payload_hash(body.requirement or ""),
    )
    if not gate.get("ok"):
        return JSONResponse(gate, status_code=400)
    out = confirm_and_start(
        workspace=body.workspace or "",
        requirement=body.requirement or "",
        client_brief=body.code_dev_brief,
        write_scope=body.write_scope,
        source_gate_job_id=body.source_gate_job_id or "",
        ui_call_id=body.ui_call_id or "",
        ui_session_id=body.ui_session_id or "",
    )
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    return out


@app.get(
    "/api/code-dev/jobs",
    tags=["本机写码"],
    summary="列出本机写码任务历史",
    description="按更新时间倒序返回任务摘要（id、状态、诉求、时间），便于核对今日测试记录。"
    "传入 ui_call_id 时只返回绑定该 DSH 工具卡的任务（刷新恢复进度用）。",
)
def api_code_dev_jobs_list(
    limit: int = Query(80, ge=1, le=200, description="最多返回条数"),
    ui_call_id: str = Query("", description="按 DSH 工具卡 callId 过滤"),
):
    from . import plugins_store
    from .code_dev.ops import FEATURE_ID, list_recent_jobs

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机 Cursor 写码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    return list_recent_jobs(limit=limit, ui_call_id=ui_call_id or "")


@app.post(
    "/api/code-dev/jobs/{job_id}/cancel",
    tags=["本机写码"],
    summary="取消本机写码任务",
    description="将 queued/running 任务标为 cancelled；后台 Cursor 线程会在下一检查点退出。"
    "引擎重启后遗留的 running 任务会在启动时自动 reconcile 为已取消。",
)
def api_code_dev_job_cancel(job_id: str):
    from . import plugins_store
    from .code_dev import cancel as code_dev_cancel
    from .code_dev.ops import FEATURE_ID

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机 Cursor 写码")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    out = code_dev_cancel(job_id)
    if not out.get("ok"):
        return JSONResponse(out, status_code=404)
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
    description="推送 status / step / token / thinking（Cursor 思考过程，含工具调用）/ tool_call / done / error。"
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
        last_live = ""
        last_think = ""
        last_delivery = ""
        last_think_ms = None
        last_progress = ""
        saw_terminal = False
        skip_replay = {"token", "token_delivery", "replace_text", "replace_delivery", "thinking"}
        interval = 0.04
        try:
            for _ in range(int(3600 / interval)):  # ~1h
                out = code_dev_get_job(jid)
                if not out.get("ok"):
                    yield f"data: {_json.dumps({'type': 'error', 'message': out.get('detail') or '找不到任务'}, ensure_ascii=False)}\n\n"
                    return
                job = out.get("job") or {}
                st = str(job.get("status") or "")
                events = job.get("events") or []
                for ev in events[last_n:]:
                    if isinstance(ev, dict) and ev.get("type"):
                        if str(ev.get("type") or "") in skip_replay:
                            continue
                        yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
                last_n = len(events)

                live = str(job.get("live_text") or "")
                if live != last_live:
                    if live.startswith(last_live):
                        delta = live[len(last_live) :]
                        if delta:
                            yield f"data: {_json.dumps({'type': 'token', 'text': delta}, ensure_ascii=False)}\n\n"
                    else:
                        yield f"data: {_json.dumps({'type': 'replace_text', 'text': live}, ensure_ascii=False)}\n\n"
                    last_live = live

                think = str(job.get("thinking_text") or "")
                think_ms = job.get("thinking_duration_ms") if st in terminal else None
                if think != last_think or think_ms != last_think_ms:
                    if think or think_ms is not None:
                        payload = {"type": "thinking", "text": think}
                        if think_ms is not None:
                            payload["thinking_duration_ms"] = think_ms
                        yield f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"
                    last_think = think
                    last_think_ms = think_ms

                delivery = str(job.get("delivery_text") or "")
                if delivery != last_delivery:
                    if last_delivery and delivery.startswith(last_delivery):
                        delta = delivery[len(last_delivery) :]
                        if delta:
                            yield f"data: {_json.dumps({'type': 'token_delivery', 'text': delta}, ensure_ascii=False)}\n\n"
                    else:
                        yield f"data: {_json.dumps({'type': 'replace_delivery', 'text': delivery}, ensure_ascii=False)}\n\n"
                    last_delivery = delivery

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
                await asyncio.sleep(interval)
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
    path_ticket: str = Field(
        "",
        description="列文件/校验成功后签发的 path_ticket；默认必填（除非 allow_agent_absolute_path）",
    )
    ui_session_id: str = Field(
        "",
        description="DSH 当前会话 sessionId；写入资料库绑定，用于点会话名精确打开",
    )


class PickFolderBody(BaseModel):
    prompt: str = "选择工程目录"


@app.post(
    "/api/pick-folder",
    tags=["本机工具"],
    summary="弹出本机选文件夹对话框",
    description="在运行引擎的本机弹出原生文件夹选择框（macOS/Windows/Linux）；"
    "仅适用于浏览器与引擎同机。一体桌面包优先走 Electron 选目录，不经过本接口。"
    "用于写码/审码确认卡「浏览…」。",
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
    from .hitl import gate_review_path

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
    gate = gate_review_path(
        local_path=body.local_path or "",
        path_ticket=body.path_ticket or "",
        allow_agent_absolute_path=cfg.allow_agent_absolute_path,
    )
    if not gate.get("ok"):
        return JSONResponse(gate, status_code=400)
    out = await run_review_async(
        local_path=body.local_path or "",
        scope=body.scope or "",
        files=body.files,
        focus=body.focus or "",
        ui_session_id=body.ui_session_id or "",
    )
    if not out.get("ok"):
        return JSONResponse(out, status_code=400)
    return out


@app.post(
    "/api/code-review/run/stream",
    tags=["本机审码"],
    summary="流式执行本机代码审查（带进度）",
    description="SSE：逐步推送校验/筛选/读码/LLM/汇总；过程中推送草稿 token，终态按行流式推送完整「代码审核汇总报告」。"
    "须带 path_ticket（企业硬门禁）。",
)
async def api_code_review_run_stream(body: CodeReviewRunBody):
    import json as _json

    from fastapi.responses import StreamingResponse

    from . import plugins_store
    from .code_review.config import get_config
    from .code_review.ops import FEATURE_ID, iter_review_events
    from .hitl import gate_review_path

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="本机目录审码")
    if blocked:
        async def err_gen():
            yield f"data: {_json.dumps({**blocked, 'type': 'done', 'ok': False}, ensure_ascii=False)}\n\n"

        return StreamingResponse(err_gen(), media_type="text/event-stream")

    cfg = get_config()
    gate = gate_review_path(
        local_path=body.local_path or "",
        path_ticket=body.path_ticket or "",
        allow_agent_absolute_path=cfg.allow_agent_absolute_path,
    )
    if not gate.get("ok"):
        async def gate_err():
            yield f"data: {_json.dumps({**gate, 'type': 'done', 'ok': False}, ensure_ascii=False)}\n\n"

        return StreamingResponse(gate_err(), media_type="text/event-stream")

    async def event_gen():
        try:
            async for ev in iter_review_events(
                local_path=body.local_path or "",
                scope=body.scope or "",
                files=body.files,
                focus=body.focus or "",
                ui_session_id=body.ui_session_id or "",
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
    nonce: str = Field("", description="确认卡签发的 HITL nonce")


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
    from .hitl import ACTION_COMMIT, require_confirm_nonce

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="人触发提交")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    gate = require_confirm_nonce(
        nonce=body.nonce or "",
        action=ACTION_COMMIT,
        job_id=body.job_id or "",
    )
    if not gate.get("ok"):
        return JSONResponse(gate, status_code=400)
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
    nonce: str = Field("", description="确认卡签发的 HITL nonce")


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
    description="仅 HITL：须带 nonce。mode=full 同步目录全量单元；mode=incremental 仅同步勾选单元。"
    "模型不得仅凭 confirmed=true 代调。",
)
def api_code_deploy_confirm(body: CodeDeployConfirmBody):
    from . import plugins_store
    from .code_deploy import confirm
    from .code_deploy.ops import FEATURE_ID
    from .hitl import ACTION_DEPLOY, require_confirm_nonce

    blocked = plugins_store.require_enabled(FEATURE_ID, capability="按插件增量部署")
    if blocked:
        return JSONResponse(blocked, status_code=400)
    gate = require_confirm_nonce(
        nonce=body.nonce or "",
        action=ACTION_DEPLOY,
        job_id=body.job_id or "",
    )
    if not gate.get("ok"):
        return JSONResponse(gate, status_code=400)
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
    description="与 engine_cli.py 命令一致：ask / pcb-ask / status / config-test-* / plugins-* / usage-summary。",
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


class AuthLoginBody(BaseModel):
    username: str = Field("", description="用户名")
    password: str = Field("", description="密码")
    enterprise_code: str = Field("", description="企业编码（展示用，本机登录可留空）")


class AuthChangePasswordBody(BaseModel):
    username: str = Field("", description="用户名（可留空，默认当前 Bearer 用户）")
    old_password: str = Field("", description="旧密码")
    new_password: str = Field("", description="新密码，至少 8 位")


def _bearer_token(request: Request) -> str:
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _live_user_row_from_bearer(request: Request):
    """校验 Bearer → users.json 存活账号。返回 (row, error_response)。"""
    from .auth import verify_token
    from .auth.users import find_user_by_id, user_is_active

    tok = _bearer_token(request)
    if not tok:
        return None, JSONResponse(
            {"ok": False, "detail": "请先登录", "code": "auth_required"},
            status_code=401,
        )
    claims = verify_token(tok)
    if not claims or not claims.get("id"):
        return None, JSONResponse(
            {"ok": False, "detail": "登录已失效，请重新登录", "code": "auth_required"},
            status_code=401,
        )
    row = find_user_by_id(str(claims.get("id") or ""))
    if not user_is_active(row):
        return None, JSONResponse(
            {"ok": False, "detail": "账号不存在或已禁用", "code": "auth_required"},
            status_code=401,
        )
    if row.get("must_change_password"):
        return None, JSONResponse(
            {
                "ok": False,
                "detail": "请先修改默认密码后再继续",
                "code": "password_change_required",
            },
            status_code=403,
        )
    return row, None


@app.post(
    "/api/auth/login",
    tags=["账号"],
    summary="本机登录",
    description="校验本机用户库账号密码，签发 JWT，并写入本机当前用户（供进程内用量流水 user_id）。"
    "用量 HTTP 接口须携带 Bearer；active.json 不作为用量 HTTP 鉴权。"
    "种子账号须改密后才可查用量。",
)
def api_auth_login(body: AuthLoginBody):
    from .auth import issue_token, public_user, set_active, verify_password

    user = verify_password(body.username or "", body.password or "")
    if not user:
        return JSONResponse(
            {"ok": False, "detail": "用户名或密码错误", "code": "auth_failed"},
            status_code=401,
        )
    pub = public_user(user) or {}
    token, exp = issue_token(
        user_id=str(pub.get("id") or ""),
        username=str(pub.get("username") or ""),
        role=str(pub.get("role") or "user"),
    )
    set_active(pub, exp=exp)
    return {
        "ok": True,
        "token": token,
        "token_type": "Bearer",
        "expires_at": exp,
        "user": pub,
        "must_change_password": bool(pub.get("must_change_password")),
    }


@app.post(
    "/api/auth/change-password",
    tags=["账号"],
    summary="修改本机密码",
    description="校验旧密码后写入新密码（至少 8 位），并清除 must_change_password。"
    "可匿名带 username，或已登录时省略 username 用 Bearer 对应用户。",
)
def api_auth_change_password(request: Request, body: AuthChangePasswordBody):
    from .auth import public_user, verify_token
    from .auth.users import change_password, find_user_by_id

    username = (body.username or "").strip()
    if not username:
        tok = _bearer_token(request)
        claims = verify_token(tok) if tok else None
        if claims and claims.get("id"):
            row = find_user_by_id(str(claims.get("id") or ""))
            username = str((row or {}).get("username") or "")
    if not username:
        return JSONResponse(
            {"ok": False, "detail": "请提供用户名或先登录", "code": "auth_required"},
            status_code=401,
        )
    if len(body.new_password or "") < 8:
        return JSONResponse(
            {"ok": False, "detail": "新密码至少 8 位", "code": "weak_password"},
            status_code=400,
        )
    row = change_password(username, body.old_password or "", body.new_password or "")
    if not row:
        return JSONResponse(
            {"ok": False, "detail": "旧密码错误或账号不可用", "code": "auth_failed"},
            status_code=401,
        )
    return {"ok": True, "user": public_user(row)}


@app.get(
    "/api/auth/me",
    tags=["账号"],
    summary="当前登录用户",
    description="优先读 Authorization: Bearer（并核对 users.json 是否仍有效）；"
    "否则读本机 active 会话（仅供登录门闸展示，不作用量 HTTP 鉴权）。未登录返回 authenticated=false。",
)
def api_auth_me(request: Request):
    from .auth import get_active_user, public_user, verify_token
    from .auth.users import find_user_by_id, user_is_active

    tok = _bearer_token(request)
    if tok:
        claims = verify_token(tok)
        if claims and claims.get("id"):
            row = find_user_by_id(str(claims.get("id") or ""))
            if user_is_active(row):
                return {
                    "ok": True,
                    "authenticated": True,
                    "user": public_user(row),
                    "source": "token",
                }
            return {
                "ok": True,
                "authenticated": False,
                "user": None,
                "detail": "账号不存在或已禁用",
                "code": "auth_required",
            }
    active = get_active_user()
    if active:
        row = find_user_by_id(str(active.get("id") or ""))
        if user_is_active(row):
            return {
                "ok": True,
                "authenticated": True,
                "user": public_user(row),
                "source": "active",
            }
    return {"ok": True, "authenticated": False, "user": None}


@app.post(
    "/api/auth/logout",
    tags=["账号"],
    summary="本机登出",
    description="清除本机当前用户会话文件；客户端应同时丢弃 localStorage 中的 token。"
    "不影响其它业务接口可用性。",
)
def api_auth_logout():
    from .auth import clear_active

    clear_active()
    return {"ok": True}


def _request_user_id(request: Request) -> str | None:
    """用量 HTTP：仅认有效 Bearer + 存活账号（不含 active.json 回落，不含须改密账号）。"""
    row, err = _live_user_row_from_bearer(request)
    if err or not row:
        return None
    return str(row.get("id") or "").strip() or None


def _request_user(request: Request) -> dict | None:
    """当前登录用户公开字段；用量场景须 Bearer。"""
    from .auth.users import public_user

    row, err = _live_user_row_from_bearer(request)
    if err or not row:
        return None
    return public_user(row)


def _require_login(request: Request):
    """个人用量等：须 Bearer + 未禁用 + 已改默认密。"""
    from .auth.users import public_user

    row, err = _live_user_row_from_bearer(request)
    if err:
        return None, err
    return public_user(row), None


def _feedback_image_magic_ok(data: bytes, suffix: str) -> bool:
    """只认真实图片头，避免把 HTML/脚本伪装成 png 落盘。"""
    if not data:
        return False
    suf = (suffix or "").lower()
    if suf == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if suf in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if suf == ".gif":
        return data.startswith(b"GIF87a") or data.startswith(b"GIF89a")
    if suf == ".webp":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if suf == ".bmp":
        return data.startswith(b"BM")
    return False


@app.get(
    "/api/about",
    tags=["账号"],
    summary="产品关于信息",
    description="返回产品名与应用版本（读 apps/zr-workbuddy/VERSION），供账号菜单「检查更新」展示。",
)
def api_about():
    return {
        "ok": True,
        "product": "ZR-WorkBuddy",
        "app_version": _app_version(),
    }


@app.post(
    "/api/feedback",
    tags=["账号"],
    summary="提交帮助与反馈",
    description="登录用户提交意见反馈（可附图片，multipart）。正文与附件清单写入 engine/data/feedback.jsonl；"
    "图片落盘 engine/data/feedback/images/（本机，不含密钥）。",
)
async def api_feedback(
    request: Request,
    message: str = Form("", description="反馈正文"),
    images: List[UploadFile] = File(default=[], description="可选截图，最多 6 张"),
):
    import re
    import time as _t
    import uuid
    from pathlib import Path

    user, err = _require_login(request)
    if err:
        return err

    msg = (message or "").strip()
    files = [f for f in (images or []) if f is not None and getattr(f, "filename", None)]

    if not msg:
        return JSONResponse({"ok": False, "detail": "请填写反馈内容"}, status_code=400)
    if len(msg) > 4000:
        return JSONResponse({"ok": False, "detail": "反馈内容请控制在 4000 字以内"}, status_code=400)
    if len(files) > 6:
        return JSONResponse({"ok": False, "detail": "最多上传 6 张图片"}, status_code=400)

    root = Path(__file__).resolve().parents[1] / "data"
    img_dir = root / "feedback" / "images"
    root.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)
    path = root / "feedback.jsonl"
    fid = uuid.uuid4().hex[:12]
    saved: list[dict] = []
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    for up in files:
        raw_name = (up.filename or "image.png").strip() or "image.png"
        suffix = Path(raw_name).suffix.lower()
        if suffix not in allowed:
            # 无后缀时按 content-type 猜测
            ct = (up.content_type or "").lower()
            if "png" in ct:
                suffix = ".png"
            elif "jpeg" in ct or "jpg" in ct:
                suffix = ".jpg"
            elif "gif" in ct:
                suffix = ".gif"
            elif "webp" in ct:
                suffix = ".webp"
            else:
                return JSONResponse(
                    {"ok": False, "detail": f"不支持的图片类型：{raw_name}"},
                    status_code=400,
                )
        data = await up.read()
        if len(data) > 5 * 1024 * 1024:
            return JSONResponse(
                {"ok": False, "detail": "单张图片请不超过 5MB"},
                status_code=400,
            )
        if not data:
            continue
        if not _feedback_image_magic_ok(data, suffix):
            return JSONResponse(
                {"ok": False, "detail": "图片内容与类型不符，请上传 png/jpg/gif/webp/bmp"},
                status_code=400,
            )
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(raw_name).stem)[:40] or "img"
        out_name = f"{fid}_{len(saved)+1}_{safe}{suffix}"
        out_path = img_dir / out_name
        try:
            out_path.write_bytes(data)
        except OSError:
            return JSONResponse(
                {"ok": False, "detail": "保存图片失败"},
                status_code=500,
            )
        saved.append(
            {
                "name": raw_name,
                "path": f"feedback/images/{out_name}",
                "bytes": len(data),
                "content_type": up.content_type or "",
            }
        )

    entry = {
        "ts": _t.strftime("%Y-%m-%dT%H:%M:%S%z") or _t.strftime("%Y-%m-%dT%H:%M:%S"),
        "id": fid,
        "user_id": str((user or {}).get("id") or ""),
        "username": str((user or {}).get("username") or ""),
        "message": msg,
        "images": saved,
    }
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return JSONResponse(
            {"ok": False, "detail": "写入反馈失败"},
            status_code=500,
        )
    return {"ok": True, "id": fid, "images": len(saved)}


def _require_admin(request: Request):
    """企业用量须有效 Bearer，且 users.json 中 role=admin（不以 active.json 单独提权）。"""
    from .auth.users import public_user

    row, err = _live_user_row_from_bearer(request)
    if err:
        return None, err
    user = public_user(row)
    if not user or str(user.get("role") or "") != "admin":
        return None, JSONResponse(
            {"ok": False, "detail": "仅管理员可查看企业用量", "code": "forbidden"},
            status_code=403,
        )
    return user, None


@app.get(
    "/api/usage/summary",
    tags=["用量统计"],
    summary="用量区间汇总",
    description="按北京时间自然日汇总**当前登录账号**的 LLM 与 Cursor token（跟账号，不跟设备）。"
    "须先登录。两条账不能加总成一笔钱。days 默认 7，最大 90。"
    "grain=day：卡片与 hourly 锚定 on 当日；monthly 为当月。"
    "grain=month：卡片为整月合计；daily/monthly 为当月逐日。"
    "本机观测：引擎直连 +（有 llm-meter 时）宿主 llm/stream 落盘；无 meter 时回退会话/记忆/标题补采。",
)
def api_usage_summary(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="回溯天数（北京时间）"),
    source: str = Query("", description="可选过滤：llm 或 cursor"),
    on: str = Query("", description="锚定自然日 YYYY-MM-DD，默认今天；卡片为该日，monthly 为当月"),
    grain: str = Query("day", description="粒度：day=锚定日分时段；month=整月逐日"),
):
    from .auth import reset_current_user, set_current_user
    from .usage import summarize
    from .usage.report import pending_count

    user, err = _require_login(request)
    if err:
        return err
    uid = str((user or {}).get("id") or "")
    g = grain if grain in {"day", "month"} else "day"
    tok = set_current_user(user)
    try:
        out = summarize(days=days, source=source, on=on, user_id=uid, grain=g)
    finally:
        reset_current_user(tok)
    try:
        out["pending_report"] = pending_count()
    except Exception:
        out["pending_report"] = 0
    # 个人用量页已去掉官网对照 UI；不在此拉取 deepseek_console（企业页另挂）
    return out


@app.post(
    "/api/usage/console-day",
    tags=["用量统计"],
    summary="录入 DeepSeek 控制台当日用量",
    description="把官网「请求次数 / Tokens / 消费金额」录入本机，用量页「DeepSeek 官网」卡片与控制台同口径。"
    "须**管理员**登录。数据存 engine/data/usage/console_days.json（全机共享对照），不含 API Key。",
)
async def api_usage_console_day(request: Request):
    from .usage.deepseek_console import save_manual_day

    user, err = _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    day = str(body.get("day") or body.get("on") or "").strip()
    try:
        calls = int(body.get("calls") or 0)
        tokens = int(body.get("tokens") or 0)
        cost = float(body.get("cost_cny") or body.get("cost") or 0)
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "detail": "calls/tokens/cost 须为数字"}, status_code=400)
    if calls < 0 or tokens < 0 or cost < 0:
        return JSONResponse({"ok": False, "detail": "数值不能为负"}, status_code=400)
    if not day:
        return JSONResponse({"ok": False, "detail": "请提供 day=YYYY-MM-DD"}, status_code=400)
    return save_manual_day(
        day=day,
        calls=calls,
        tokens=tokens,
        cost_cny=cost,
        note=str(body.get("note") or ""),
    )

@app.get(
    "/api/usage/events",
    tags=["用量统计"],
    summary="用量流水分页",
    description="按时间倒序返回**当前登录账号**的流水（无 API Key）。须先登录。默认每页 10 条。"
    "quality=session 为 DSH 宿主会话，sdk 为 Cursor SDK，missing 表示未回传 token。",
)
def api_usage_events(
    request: Request,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(10, ge=1, le=50, description="每页条数，默认 10"),
    source: str = Query("", description="可选过滤：llm 或 cursor"),
    on: str = Query("", description="可选，只看该自然日 YYYY-MM-DD"),
    limit: int | None = Query(None, ge=1, le=200, description="兼容旧参数，传入时覆盖每页条数"),
):
    from .auth import reset_current_user, set_current_user
    from .usage import list_events

    user, err = _require_login(request)
    if err:
        return err
    uid = str((user or {}).get("id") or "")
    size = int(limit or page_size)
    tok = set_current_user(user)
    try:
        return list_events(page=page, page_size=size, source=source, limit=size, on=on, user_id=uid)
    finally:
        reset_current_user(tok)


@app.get(
    "/api/usage/daily",
    tags=["用量统计"],
    summary="按日用量序列",
    description="近 N 天每天的 LLM token 与 Cursor token 分列（**当前登录账号**），供折线/柱状展示。"
    "须先登录。on 与 summary 相同，锚定区间末日。",
)
def api_usage_daily(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="回溯天数（北京时间）"),
    on: str = Query("", description="锚定自然日 YYYY-MM-DD，默认今天"),
):
    from .usage import summarize

    user, err = _require_login(request)
    if err:
        return err
    uid = str((user or {}).get("id") or "")
    s = summarize(days=days, on=on, user_id=uid)
    return {
        "ok": True,
        "days": s.get("days"),
        "tz": s.get("tz"),
        "from": s.get("from"),
        "to": s.get("to"),
        "user_id": s.get("user_id") or "",
        "daily": s.get("daily") or [],
    }


@app.post(
    "/api/usage-hub/v1/ingest",
    tags=["企业用量汇总"],
    summary="接收本机用量上报",
    description="按事件 id 幂等入库。Authorization: Bearer 使用 config usage.report_token。"
    "失败不得回写本机业务；本机上报客户端超时短、失败下次再报。",
)
async def api_usage_hub_ingest(request: Request):
    from . import usage_hub

    if not usage_hub.check_ingest_token(request.headers.get("authorization")):
        return JSONResponse(
            {"ok": False, "detail": "机器票据无效", "code": "bad_token", "accepted": [], "duplicate": []},
            status_code=401,
        )
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "detail": "JSON 无效", "accepted": [], "duplicate": []},
            status_code=400,
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            {"ok": False, "detail": "body 须为对象", "accepted": [], "duplicate": []},
            status_code=400,
        )
    return usage_hub.ingest_batch(payload)


@app.get(
    "/api/usage-hub/v1/company",
    tags=["企业用量汇总"],
    summary="公司 LLM / Cursor 合计",
    description="须管理员登录。管理页优先走 /api/usage/enterprise/*；本接口与之同权，禁止匿名读取。",
)
def api_usage_hub_company(
    request: Request,
    from_date: str = Query("", alias="from", description="起始自然日 YYYY-MM-DD（北京时间）"),
    to_date: str = Query("", alias="to", description="结束自然日 YYYY-MM-DD（北京时间）"),
):
    from . import usage_hub

    _, err = _require_admin(request)
    if err:
        return err
    return usage_hub.company_summary(from_date=from_date, to_date=to_date)


@app.get(
    "/api/usage-hub/v1/people",
    tags=["企业用量汇总"],
    summary="按人日/月序列",
    description="须管理员登录。Cursor 永不计入公司 Key 总额。禁止匿名读取。",
)
def api_usage_hub_people(
    request: Request,
    from_date: str = Query("", alias="from", description="起始自然日 YYYY-MM-DD"),
    to_date: str = Query("", alias="to", description="结束自然日 YYYY-MM-DD"),
    grain: str = Query("month", description="粒度：day 或 month"),
):
    from . import usage_hub

    _, err = _require_admin(request)
    if err:
        return err
    return usage_hub.people_summary(from_date=from_date, to_date=to_date, grain=grain)


@app.get(
    "/api/usage/enterprise/summary",
    tags=["企业用量汇总"],
    summary="管理页·企业用量总览（同个人汇总形态）",
    description="须管理员登录。返回形态与 /api/usage/summary 相同，但统计**全部账号**。"
    "grain=day：卡片/分时段锚定 on 当日；grain=month：卡片为整月合计，分时段为当月同时段累加。"
    "LLM 与 Cursor 仍分列，不能加总成一笔钱。",
)
def api_usage_enterprise_summary(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="回溯天数（北京时间）"),
    source: str = Query("", description="可选过滤：llm 或 cursor"),
    on: str = Query("", description="锚定自然日 YYYY-MM-DD，默认今天"),
    grain: str = Query("day", description="粒度：day=锚定日卡片/分时段；month=整月合计与当月分时段累加"),
):
    from .usage import summarize
    from .usage.report import pending_count

    _, err = _require_admin(request)
    if err:
        return err
    g = grain if grain in {"day", "month"} else "day"
    out = summarize(days=days, source=source, on=on, user_id=None, grain=g)
    out["scope"] = "enterprise"
    try:
        out["pending_report"] = pending_count()
    except Exception:
        out["pending_report"] = 0
    try:
        from .usage.deepseek_console import fetch_console_day

        out["deepseek_console"] = fetch_console_day(
            on=str(out.get("on") or on or ""),
            local=out.get("today") if isinstance(out.get("today"), dict) else None,
        )
    except Exception:
        out["deepseek_console"] = {
            "ok": False,
            "configured": False,
            "detail": "官网对照不可用",
        }
    return out


@app.get(
    "/api/usage/enterprise/company",
    tags=["企业用量汇总"],
    summary="管理页·公司合计",
    description="须管理员登录。数据来自本机汇总库（P0 与引擎同进程）。",
)
def api_usage_enterprise_company(
    request: Request,
    from_date: str = Query("", alias="from", description="起始自然日 YYYY-MM-DD"),
    to_date: str = Query("", alias="to", description="结束自然日 YYYY-MM-DD"),
):
    from . import usage_hub

    _, err = _require_admin(request)
    if err:
        return err
    return usage_hub.company_summary(from_date=from_date, to_date=to_date)


@app.get(
    "/api/usage/enterprise/people",
    tags=["企业用量汇总"],
    summary="管理页·按人序列",
    description="须管理员登录。grain=day|month。",
)
def api_usage_enterprise_people(
    request: Request,
    from_date: str = Query("", alias="from", description="起始自然日 YYYY-MM-DD"),
    to_date: str = Query("", alias="to", description="结束自然日 YYYY-MM-DD"),
    grain: str = Query("month", description="粒度：day 或 month"),
):
    from . import usage_hub

    _, err = _require_admin(request)
    if err:
        return err
    return usage_hub.people_summary(from_date=from_date, to_date=to_date, grain=grain)


@app.post(
    "/api/usage/report-now",
    tags=["用量统计"],
    summary="立即尝试上报待报流水",
    description="须已登录。失败只返回摘要，不影响聊天/写码。report_enabled 关闭时跳过。",
)
def api_usage_report_now(request: Request):
    from .usage.report import flush_report

    _, err = _require_login(request)
    if err:
        return err
    return flush_report(force=True)


class SpacePurgeBody(BaseModel):
    dry_run: bool = Field(False, description="仅统计将清理的条数，不真正删除")
    retention_days: int | None = Field(
        None,
        description="临时覆盖配置中的保留天数；空则用 config space.retention_days",
    )


def _space_can_access(row_user_id: str, me: dict, *, admin: bool) -> bool:
    if admin:
        return True
    return str(row_user_id or "") == str((me or {}).get("id") or "")


@app.get(
    "/api/space/status",
    tags=["资料库"],
    summary="空间占用与保留策略",
    description="须登录。返回当前用户会话/文档条数、字节占用与保留天数。"
    "资料库仅本机；不当聊天续聊权威。不做外部同步（同步在列表接口）。",
)
def api_space_status(request: Request):
    from .space import get_space_config, status_counts

    me, err = _require_login(request)
    if err:
        return err
    # 不同步外部草稿：列表接口会 sync；此处只读计数，避免打开资料库时双倍扫盘卡顿
    cfg = get_space_config()
    counts = status_counts(user_id=str(me.get("id") or ""), admin_all=False)
    return {"ok": True, **counts, "config": cfg}


@app.get(
    "/api/space/sessions",
    tags=["资料库"],
    summary="会话档案列表",
    description="须登录。列出本机「我的空间」中的会话摘要档案（非 DSH 续聊列表）。"
    "打开列表前会 fail-soft 同步本机 PCB 8D 草稿目录（~/.zhongruan/pcb-8d-drafts）。",
)
def api_space_sessions(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移"),
):
    from .space import list_sessions, sync_external_into_space

    me, err = _require_login(request)
    if err:
        return err
    try:
        sync_external_into_space(user_id=str(me.get("id") or ""))
    except Exception:
        pass
    rows = list_sessions(user_id=str(me.get("id") or ""), limit=limit, offset=offset)
    # 列表不回传超长正文
    slim = []
    for r in rows:
        item = {**r}
        body = str(item.get("body_text") or "")
        if len(body) > 400:
            item["body_preview"] = body[:400] + "…"
        else:
            item["body_preview"] = body
        item.pop("body_text", None)
        slim.append(item)
    return {"ok": True, "sessions": slim}


@app.get(
    "/api/space/sessions/{session_id}",
    tags=["资料库"],
    summary="会话档案详情",
    description="须登录。含会话摘要正文与下属文档列表。",
)
def api_space_session_detail(request: Request, session_id: str):
    from .space import get_session, list_artifacts

    me, err = _require_login(request)
    if err:
        return err
    row = get_session(session_id)
    if not row or not _space_can_access(str(row.get("user_id") or ""), me, admin=False):
        return JSONResponse({"ok": False, "detail": "会话档案不存在"}, status_code=404)
    arts = list_artifacts(
        user_id=str(me.get("id") or ""),
        session_id=str(row.get("id") or ""),
        limit=200,
    )
    return {"ok": True, "session": row, "artifacts": arts}


@app.get(
    "/api/space/sessions/{session_id}/locate-dsh",
    tags=["资料库"],
    summary="打开已绑定的 DSH 会话",
    description="须登录。只返回入库时写死的 session-uuid（dsh_path / 档案 id）；"
    "不做内容启发式反查，避免多个相似会话误命中。未绑定则 dsh_session_id 为空。",
)
def api_space_session_locate_dsh(request: Request, session_id: str):
    from .space import get_session, locate_dsh_session

    me, err = _require_login(request)
    if err:
        return err
    row = get_session(session_id)
    if not row or not _space_can_access(str(row.get("user_id") or ""), me, admin=False):
        return JSONResponse({"ok": False, "detail": "会话档案不存在"}, status_code=404)
    sid = str(row.get("id") or session_id)
    loc = locate_dsh_session(
        catalog_id=sid,
        cached_dsh_id=str(row.get("dsh_path") or ""),
    )
    return {"ok": True, **loc}


@app.delete(
    "/api/space/sessions/{session_id}",
    tags=["资料库"],
    summary="删除会话档案",
    description="须登录。删除本机空间中的会话摘要及级联文档；不删除 DSH 左侧原会话。",
)
def api_space_session_delete(request: Request, session_id: str):
    from .space import delete_session, get_session

    me, err = _require_login(request)
    if err:
        return err
    row = get_session(session_id)
    if not row or not _space_can_access(str(row.get("user_id") or ""), me, admin=False):
        return JSONResponse({"ok": False, "detail": "会话档案不存在"}, status_code=404)
    ok = delete_session(session_id, user_id=str(me.get("id") or ""), cascade_artifacts=True)
    return {"ok": bool(ok)}


@app.get(
    "/api/space/library",
    tags=["资料库"],
    summary="按会话列出资料库",
    description="须登录。只返回至少有一份文档的会话；每页默认 10 个会话；"
    "按会话下最新文档时间倒序（新的在前）。"
    "打开前会 fail-soft 同步 PCB 8D / 聊天文档，并清理无文档的空会话标题。",
)
def api_space_library(
    request: Request,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(10, ge=1, le=50, description="每页会话数，默认 10"),
    q: str = Query("", description="可选：按会话/文档标题搜索"),
    limit: int = Query(0, ge=0, le=200, description="兼容旧参数；若 >0 则当作 page_size"),
):
    from .space import list_library, purge_empty_sessions, sync_external_into_space

    me, err = _require_login(request)
    if err:
        return err
    try:
        sync_external_into_space(user_id=str(me.get("id") or ""))
    except Exception:
        pass
    try:
        purge_empty_sessions(user_id=str(me.get("id") or ""))
    except Exception:
        pass
    from .space.dsh_locate import bound_dsh_session_id

    display = str(me.get("display_name") or me.get("username") or "").strip()
    ps = int(limit) if limit and limit > 0 else page_size
    packed = list_library(
        user_id=str(me.get("id") or ""),
        page=page,
        page_size=ps,
        q=q or "",
    )
    tree = packed.get("sessions") or []
    for item in tree:
        item["display_name"] = display or str(item.get("user_id") or "")
        dsh = bound_dsh_session_id(
            catalog_id=str(item.get("id") or ""),
            dsh_path=str(item.get("dsh_path") or ""),
        )
        item["dsh_session_id"] = dsh
        item["openable"] = bool(dsh)
        for art in item.get("artifacts") or []:
            if isinstance(art, dict) and not art.get("display_name"):
                art["display_name"] = display or str(art.get("user_id") or "")
    return {
        "ok": True,
        "sessions": tree,
        "display_name": display,
        "total": int(packed.get("total") or 0),
        "page": int(packed.get("page") or page),
        "page_size": int(packed.get("page_size") or ps),
    }


@app.get(
    "/api/space/artifacts",
    tags=["资料库"],
    summary="文档列表",
    description="须登录。扁平列出报告等文档（含审码报告历史）。",
)
def api_space_artifacts(
    request: Request,
    kind: str = Query("", description="可选类型过滤，如 code_review_report / pcb_8d_report"),
    session_id: str = Query("", description="可选会话 id"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移"),
):
    from .space import list_artifacts, sync_external_into_space

    me, err = _require_login(request)
    if err:
        return err
    try:
        sync_external_into_space(user_id=str(me.get("id") or ""))
    except Exception:
        pass
    rows = list_artifacts(
        user_id=str(me.get("id") or ""),
        kind=kind,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, "artifacts": rows}


@app.get(
    "/api/space/artifacts/{artifact_id}",
    tags=["资料库"],
    summary="打开文档正文",
    description="须登录。返回元数据与正文（报告 markdown 等）。",
)
def api_space_artifact_get(request: Request, artifact_id: str):
    from .space import get_artifact
    from .space.catalog import read_artifact_body

    me, err = _require_login(request)
    if err:
        return err
    row = get_artifact(artifact_id)
    if not row or not _space_can_access(str(row.get("user_id") or ""), me, admin=False):
        return JSONResponse({"ok": False, "detail": "文档不存在"}, status_code=404)
    body = read_artifact_body(row)
    return {"ok": True, "artifact": row, "body": body}


@app.delete(
    "/api/space/artifacts/{artifact_id}",
    tags=["资料库"],
    summary="删除文档",
    description="须登录。删除空间内文档文件与目录项。",
)
def api_space_artifact_delete(request: Request, artifact_id: str):
    from .space import delete_artifact, get_artifact

    me, err = _require_login(request)
    if err:
        return err
    row = get_artifact(artifact_id)
    if not row or not _space_can_access(str(row.get("user_id") or ""), me, admin=False):
        return JSONResponse({"ok": False, "detail": "文档不存在"}, status_code=404)
    ok = delete_artifact(artifact_id, user_id=str(me.get("id") or ""))
    return {"ok": bool(ok)}


@app.post(
    "/api/space/purge",
    tags=["资料库"],
    summary="按保留策略清理",
    description="须登录。清理当前用户过期会话档案与文档；dry_run=true 时只统计。",
)
def api_space_purge(request: Request, body: SpacePurgeBody):
    from .space import purge_expired

    me, err = _require_login(request)
    if err:
        return err
    return purge_expired(
        user_id=str(me.get("id") or ""),
        dry_run=bool(body.dry_run),
        retention_days=body.retention_days,
    )


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
    description="写入 plugins.json；mes-bridge 约 1.5s 内 ctx.plugin 加载，无需重启 DSH。"
    "启用 code-dev 时会互斥停用 DSH「Cursor 写码」插件（profile disabledBundles）。",
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


@app.post(
    "/api/plugins/preflight",
    tags=["功能热插拔"],
    summary="安装前校验第三方插件",
    description="对本地目录路径或上传的 zip 做契约校验，不写入 features/。"
    "multipart 字段名 file；或 query path=。业务验收看引擎页，不依赖 DSH。",
)
async def api_plugins_preflight(
    file: UploadFile | None = File(None),
    path: str = Query("", description="本机 feature 目录或 zip 路径"),
):
    from . import feature_install

    if file is not None and (file.filename or "").strip():
        import tempfile

        suffix = ".zip" if (file.filename or "").lower().endswith(".zip") else ".bin"
        os.makedirs(feature_install.install_tmp_dir(), exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix="feat-up-", suffix=suffix, dir=feature_install.install_tmp_dir()
        )
        os.close(fd)
        try:
            data = await file.read()
            with open(tmp, "wb") as f:
                f.write(data)
            return feature_install.preflight_path(tmp)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return feature_install.preflight_path(path)


@app.post(
    "/api/plugins/install",
    tags=["功能热插拔"],
    summary="安装第三方功能插件",
    description="校验通过后原子落入 features/<id>/ 并默认 enable。"
    "支持 multipart zip（字段 file）或 path 指向目录/zip；force 可覆盖已有 id。",
)
async def api_plugins_install(
    file: UploadFile | None = File(None),
    path: str = Query("", description="本机 feature 目录或 zip 路径"),
    force: bool = Query(False, description="覆盖已存在的 features/<id>"),
    enable: bool = Query(True, description="安装后是否写入 enable"),
):
    from . import feature_install

    if file is not None and (file.filename or "").strip():
        import tempfile

        os.makedirs(feature_install.install_tmp_dir(), exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix="feat-up-", suffix=".zip", dir=feature_install.install_tmp_dir()
        )
        os.close(fd)
        try:
            data = await file.read()
            with open(tmp, "wb") as f:
                f.write(data)
            return feature_install.install_from_zip(tmp, force=force, enable=enable)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return feature_install.install_source(path, force=force, enable=enable)


@app.delete(
    "/api/plugins/{plugin_id}",
    tags=["功能热插拔"],
    summary="停用或卸载功能插件",
    description="默认仅 disable；purge=true 时将 features/<id>/ 移入 engine/data/feature_quarantine/。",
)
def api_plugins_uninstall(
    plugin_id: str,
    purge: bool = Query(False, description="移入隔离区并删除 features 下目录"),
):
    from . import feature_install

    return feature_install.uninstall_feature(plugin_id, purge=purge)


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

@app.get("/zr-logo.svg", include_in_schema=False)
def zr_logo():
    return FileResponse(os.path.join(STATIC_DIR, "zr-logo.svg"))


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
