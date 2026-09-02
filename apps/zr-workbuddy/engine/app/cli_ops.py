"""与 engine_cli / HTTP /api/cli 共用的命令实现。"""

from __future__ import annotations

from .analyzer import analyze
from .config_store import load_config
from .demo_data import get_demo_store
from .health import check_net, llm_ready
from .mes_analyzer import analyze_mes
from .mes_client import MesError
from .nl_engine import llm_chat, parse_question
from . import plugins_store

# feature id ↔ 能力：面板 chat / CLI / Agent 工具必须共用同一启停门闸
FEATURE_ASK = "mes-ask"
FEATURE_CONFIG = "mes-config"
FEATURE_PCB = "mes-pcb"
FEATURE_CODE_DEV = "code-dev"


def _ask_disabled_chat_response() -> dict:
    hint = plugins_store.disabled_hint(FEATURE_ASK, capability="MES 自然语言查数")
    return {
        "ok": True,
        "reply": hint,
        "thinking": "",
        "chart": None,
        "table": None,
        "note": "mes-ask 未启用",
        "source": "disabled",
        "data_source": "assistant",
        "intent": {"type": "disabled", "metric": "", "dim": None, "chart": None},
    }


async def chat_stream(text: str, *, code_dev_brief: dict | None = None):
    """流式聊天事件生成器（供 /api/chat/stream）。
    yield dict：status|thinking|reply|meta|error|done
    """
    text = (text or "").strip()
    if not text:
        yield {"type": "error", "detail": "问题不能为空"}
        return

    from .pcb_expert import feature_enabled, is_pcb_question, pcb_ask_stream
    from .code_dev import handle_chat_code_dev, is_code_dev_question

    def _emit_code_dev(out: dict):
        """统一写码结果事件（含 code_dev_ui，禁止丢卡）。"""
        thinking = out.get("thinking") or ""
        events = []
        if thinking:
            events.append({"type": "thinking", "text": thinking})
        if out.get("reply"):
            events.append({"type": "reply", "delta": out["reply"]})
        intent = out.get("intent") or {"type": "code_dev", "metric": "", "dim": None, "chart": None}
        note = out.get("note")
        ui = out.get("code_dev_ui")
        events.append(
            {
                "type": "done",
                "ok": True,
                "reply": out.get("reply") or "",
                "thinking": thinking,
                "chart": None,
                "table": None,
                "note": note,
                "source": out.get("source") or "code_dev",
                "data_source": out.get("data_source") or "code_dev",
                "intent": intent,
                "job_id": out.get("job_id"),
                "code_dev_ui": ui,
                "code_dev_brief": out.get("code_dev_brief"),
            }
        )
        return events

    # 写码意图：需求收集 → 思考 + 选项/确认卡（确认后才开工，绝不在此 start）
    if is_code_dev_question(text) and plugins_store.is_enabled(FEATURE_CODE_DEV):
        yield {"type": "status", "detail": "正在梳理写码需求…"}
        out = await handle_chat_code_dev(text, client_brief=code_dev_brief)
        for ev in _emit_code_dev(out):
            yield ev
        return

    if is_pcb_question(text) and feature_enabled():
        async for ev in pcb_ask_stream(text):
            if ev.get("type") == "done" and ev.get("ok"):
                yield {
                    **ev,
                    "data_source": "pcb_expert",
                    "intent": {"type": "pcb_chat", "metric": "", "dim": None, "chart": None},
                    "chart": None,
                    "table": None,
                }
            else:
                yield ev
        return

    # PCB 问题但 feature 已停用：明确提示（不误走 MES 查数、也不偷偷调专家）
    if is_pcb_question(text) and not feature_enabled():
        from .pcb_expert import DISABLED_HINT

        yield {"type": "reply", "delta": DISABLED_HINT}
        yield {
            "type": "done",
            "ok": True,
            "reply": DISABLED_HINT,
            "thinking": "",
            "source": "disabled",
            "data_source": "pcb_expert",
            "intent": {"type": "pcb_chat", "metric": "", "dim": None, "chart": None},
            "note": "mes-pcb 未启用",
            "chart": None,
            "table": None,
        }
        return

    # MES 查数：须 mes-ask 已启用（与 Agent 工具 mes_ask 同一真相源）
    if not plugins_store.is_enabled(FEATURE_ASK):
        out = _ask_disabled_chat_response()
        yield {"type": "reply", "delta": out["reply"]}
        yield {
            "type": "done",
            "ok": True,
            "reply": out["reply"],
            "thinking": "",
            "chart": None,
            "table": None,
            "note": out.get("note"),
            "source": "disabled",
            "data_source": out.get("data_source"),
            "intent": out.get("intent"),
        }
        return

    # MES 查数：先提示再一次性返回完整结果（规则/分析路径不便 token 流）
    # 注意：LLM 可能中途判成写码 → chat() 返回 code_dev，必须透传 code_dev_ui
    yield {"type": "status", "detail": "正在查询与分析…"}
    out = await chat(text)
    if not out.get("ok"):
        yield {"type": "error", "detail": out.get("detail") or "查询失败"}
        return
    if (
        out.get("code_dev_ui")
        or out.get("source") == "code_dev"
        or (out.get("intent") or {}).get("type") == "code_dev"
    ):
        for ev in _emit_code_dev(out):
            yield ev
        return
    if out.get("thinking"):
        yield {"type": "thinking", "text": out["thinking"]}
    if out.get("reply"):
        yield {"type": "reply", "delta": out["reply"]}
    yield {
        "type": "done",
        "ok": True,
        "reply": out.get("reply") or "",
        "thinking": out.get("thinking") or "",
        "chart": out.get("chart"),
        "table": out.get("table"),
        "note": out.get("note"),
        "source": out.get("source"),
        "data_source": out.get("data_source"),
        "intent": out.get("intent"),
        "llm_tried": out.get("llm_tried"),
        "llm_error": out.get("llm_error"),
        "code_dev_ui": out.get("code_dev_ui"),
    }


async def chat(text: str, *, code_dev_brief: dict | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        return {"ok": False, "detail": "问题不能为空"}

    from .code_dev import handle_chat_code_dev, is_code_dev_question
    from .pcb_expert import chat_response, is_pcb_question, pcb_ask

    if is_code_dev_question(text) and plugins_store.is_enabled(FEATURE_CODE_DEV):
        return await handle_chat_code_dev(text, client_brief=code_dev_brief)

    # PCB 工艺问题：仅当 mes-pcb feature 已启用才走专家（热插拔真相源 = plugins.json）
    if is_pcb_question(text):
        return chat_response(await pcb_ask(text))

    # MES 自然语言查数：须 mes-ask 已启用（面板与 Agent 同源）
    if not plugins_store.is_enabled(FEATURE_ASK):
        return _ask_disabled_chat_response()

    cfg = load_config()
    intent = parse_question(text)
    source = "rule"
    llm_tried = False
    llm_error = None
    llm_cfg = cfg.get("deepseek") or {}
    if llm_ready(cfg):
        llm_tried = True
        mes_connected = bool((cfg.get("mes") or {}).get("base_url"))
        context = ("数据源：MES 实时（已连接 ERP 系统）" if mes_connected
                   else "数据源：演示数据（未连接 MES，查数据会返回演示数据）")
        r = await llm_chat(text, llm_cfg, context)
        if r and r.get("kind") == "code_dev":
            return await handle_chat_code_dev(text, client_brief=code_dev_brief)
        if r and r.get("kind") == "query" and r.get("intent"):
            intent = r["intent"]
            source = "llm"
        elif r and r.get("kind") == "chat":
            return {"ok": True, "reply": r["reply"], "chart": None, "table": None,
                    "note": None, "source": "llm", "data_source": "assistant",
                    "intent": {"type": "chat", "metric": "", "dim": None, "chart": None}}
        else:
            provider = (llm_cfg.get("provider") or "deepseek").lower()
            llm_error = ("LLM 未连通（DeepSeek API 需要外网）→ 已用规则引擎"
                         if provider == "deepseek" and not check_net()
                         else "LLM 未返回有效意图 → 已用规则引擎")

    special = {
        "greeting": "👋 你好！我是 ZR-WorkBuddy。\n想知道什么？比如：「今天完工工单数量」「最近7天各产线产量对比」。",
        "thanks": "不客气！还有想问的随时找我 😊",
        "help": "我是 ZR-WorkBuddy 工作助手，可帮你查生产数据：产量/良率/不良率/OEE/缺陷/工单（完工、在制、总数），支持趋势/对比/排名/占比/原因分析。也可以问概念，如「OEE是什么」。",
        "unknown": "😅 没完全理解你的问题。可以这样问我：\n• 今天完工工单数量\n• 今天正在生产的工单有多少个\n• 最近7天各产线产量对比\n• 分析8月30号良率过低的原因",
    }
    if intent.get("type") in special:
        return {"ok": True, "reply": special[intent["type"]], "chart": None,
                "table": None, "note": None, "source": source,
                "data_source": "assistant",
                "intent": {"type": intent["type"], "metric": "", "dim": None, "chart": None}}

    mes = cfg.get("mes") or {}
    data_source = "demo"
    note_extra = None
    result = None
    if mes.get("base_url"):
        try:
            result = await analyze_mes(intent, mes)
            data_source = "mes"
        except MesError as e:
            note_extra = f"MES 查询失败：{e}"
        except Exception as e:
            note_extra = f"MES 查询异常：{type(e).__name__}: {e}"
    if result is None:
        store = get_demo_store()
        result = analyze(store, intent)
        data_source = "demo"
        if note_extra:
            result["note"] = ((result.get("note") or "") + " " + note_extra).strip()

    return {
        "ok": True,
        "reply": result["reply"],
        "chart": result.get("chart"),
        "table": result.get("table"),
        "note": result.get("note"),
        "source": source,
        "data_source": data_source,
        "llm_tried": llm_tried,
        "llm_error": llm_error,
        "intent": {"metric": intent["metric"], "dim": intent["dim"], "type": intent["type"],
                   "chart": intent["chart"], "range_desc": intent["range_desc"],
                   "filters": intent["filters"]},
    }


async def run_async(cmd: str, rest: list[str]) -> dict:
    if cmd == "ask":
        blocked = plugins_store.require_enabled(FEATURE_ASK, capability="MES 自然语言查数")
        if blocked:
            # 与面板一致：可读提示；Agent resultRender 用 detail/reply
            hint = blocked["detail"]
            return {
                "ok": True,
                "reply": hint,
                "thinking": "",
                "chart": None,
                "table": None,
                "note": blocked.get("note"),
                "source": "disabled",
                "data_source": "assistant",
                "detail": hint,
            }
        out = await chat(" ".join(rest) if rest else "")
        if not out.get("ok"):
            return {"ok": False, "detail": out.get("detail") or "问题为空"}
        return out
    if cmd == "pcb-ask":
        from .pcb_expert import pcb_ask
        return await pcb_ask(" ".join(rest) if rest else "")
    if cmd == "status":
        blocked = plugins_store.require_enabled(FEATURE_CONFIG, capability="MES / LLM 连接状态")
        if blocked:
            return blocked
        from .status_info import build_status
        return build_status(include_demo=False)
    if cmd == "config-test-mes":
        blocked = plugins_store.require_enabled(FEATURE_CONFIG, capability="MES 连接测试")
        if blocked:
            return blocked
        from .mes_client import probe_connection
        cfg = load_config()
        return await probe_connection(cfg.get("mes") or {})
    if cmd == "config-test-llm":
        blocked = plugins_store.require_enabled(FEATURE_CONFIG, capability="LLM 连接测试")
        if blocked:
            return blocked
        cfg = load_config()
        llm = cfg.get("deepseek") or {}
        provider = (llm.get("provider") or "deepseek").lower()
        if provider == "none":
            return {"ok": False, "detail": "LLM 引擎未启用（provider=none）"}
        if provider == "ollama" and not (llm.get("model") or "").strip():
            return {"ok": False, "detail": "Ollama 未配置模型名"}
        if provider == "deepseek" and not (llm.get("api_key") or "").strip():
            return {"ok": False, "detail": "DeepSeek 未配置 API Key"}
        try:
            r = await llm_chat("你好", llm, "环境：连接测试")
            return {"ok": r is not None,
                    "detail": f"LLM 引擎可用（{provider} / {llm.get('model')}）"
                    if r else "LLM 调用失败（未返回有效响应）"}
        except Exception as e:
            return {"ok": False, "detail": f"LLM 调用异常：{type(e).__name__}: {e}"}
    if cmd == "plugins-list":
        return plugins_store.snapshot()
    if cmd == "plugins-enable":
        fid = rest[0] if rest else ""
        return plugins_store.enable(fid)
    if cmd == "plugins-disable":
        fid = rest[0] if rest else ""
        return plugins_store.disable(fid)
    if cmd == "code-dev-status":
        blocked = plugins_store.require_enabled(FEATURE_CODE_DEV, capability="本机 Cursor 写码")
        if blocked:
            return blocked
        from .code_dev import status as code_dev_status
        return code_dev_status()
    if cmd == "code-dev-check":
        blocked = plugins_store.require_enabled(FEATURE_CODE_DEV, capability="本机 Cursor 写码")
        if blocked:
            return blocked
        from .code_dev import check_workspace
        return check_workspace(" ".join(rest) if rest else "")
    if cmd == "code-dev-start":
        blocked = plugins_store.require_enabled(FEATURE_CODE_DEV, capability="本机 Cursor 写码")
        if blocked:
            return blocked
        from .code_dev import start as code_dev_start
        # args: <workspace绝对路径> | <需求…>
        # 约定：第一个参数为路径，其余为空格拼成需求；也可用 JSON 单参（由 HTTP 传）
        if not rest:
            return {"ok": False, "detail": "用法: code-dev-start <workspace绝对路径> <需求>"}
        workspace = rest[0]
        message = " ".join(rest[1:]).strip()
        return code_dev_start(workspace=workspace, message=message)
    if cmd == "code-dev-job":
        blocked = plugins_store.require_enabled(FEATURE_CODE_DEV, capability="本机 Cursor 写码")
        if blocked:
            return blocked
        from .code_dev import get_job as code_dev_get_job
        return code_dev_get_job(rest[0] if rest else "")
    if cmd == "code-dev-cancel":
        blocked = plugins_store.require_enabled(FEATURE_CODE_DEV, capability="本机 Cursor 写码")
        if blocked:
            return blocked
        from .code_dev import cancel as code_dev_cancel
        return code_dev_cancel(rest[0] if rest else "")
    if cmd == "code-dev-confirm":
        # 确认卡点「开始」后调用；args: <workspace> <requirement…>
        blocked = plugins_store.require_enabled(FEATURE_CODE_DEV, capability="本机 Cursor 写码")
        if blocked:
            return blocked
        from .code_dev.chat_bridge import confirm_and_start
        if not rest:
            return {"ok": False, "detail": "用法: code-dev-confirm <workspace绝对路径> <需求>"}
        return confirm_and_start(workspace=rest[0], requirement=" ".join(rest[1:]).strip())
    return {"ok": False, "detail": f"未知命令: {cmd}"}
