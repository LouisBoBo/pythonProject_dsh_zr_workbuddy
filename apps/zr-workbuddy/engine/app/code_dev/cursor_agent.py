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
    msg = str(
        getattr(message, "message", None)
        or (message.get("message") if isinstance(message, dict) else None)
        or ""
    ).strip()
    return mtype, status, msg


def _assistant_text_from_message(message: Any) -> str:
    text = getattr(message, "text", None)
    if text:
        return str(text)
    if isinstance(message, dict):
        return str(message.get("text") or message.get("content") or "")
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("text", "output_text"):
                parts.append(str(block.get("text") or ""))
            else:
                t = getattr(block, "text", None)
                if t:
                    parts.append(str(t))
        return "".join(parts)
    return ""


def _merge_assistant_delta(prev: str, piece: str) -> tuple[str, str, bool]:
    """返回 (full, delta, replaced)。"""
    p = prev or ""
    n = piece or ""
    if not n:
        return p, "", False
    if not p:
        return n, n, False
    if n.startswith(p):
        return n, n[len(p) :], False
    if p.endswith(n) or n in p:
        return p, "", False
    return n, n, True


def build_prompt(*, requirement: str, workspace_hint: str, empty_target: bool) -> str:
    mode = (
        "空目录新项目：请从零生成可运行的最小实现"
        if empty_target
        else "已有工程（工作区即沙箱拷贝）：请在现有结构上增量修改"
    )
    req = (requirement or "").strip()
    return (
        "你正在 ZR-WorkBuddy 的本机写码沙箱中执行改码任务。\n"
        "【工作区】当前 cwd 就是沙箱根目录，请直接读写此目录内文件。\n"
        f"【目标模式】{mode}\n"
        f"【用户确认的本机同步目录（勿当作 cwd；任务成功后由系统同步）】{workspace_hint}\n\n"
        "规则：\n"
        "1. **只改本工作区（cwd）内文件**。禁止读写宿主机家目录、`.ssh`、`.env`、密钥。\n"
        "2. 最小必要改动。\n"
        "3. 结束后用简短中文说明改了哪些文件与如何验收。\n\n"
        f"【需求】\n{req}\n"
    )


def run_cursor_local_agent(
    *,
    sandbox: Path,
    prompt: str,
    sink: Sink | None,
    step: Callable[..., None],
    is_cancel_requested: Callable[[], bool],
    timeout_sec: int = 2700,
) -> dict[str, Any]:
    """返回 {ok, text, agent_id, run_id, error}。"""
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
    model = cfg.model
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

    step("Cursor 本机 Agent 启动…", sid="cursor-local", state="running")
    _emit(
        sink,
        {
            "type": "status",
            "text": f"Cursor Local（model={model}）",
            "phase": "agent",
        },
    )

    final_text = ""
    agent_id = ""
    run_id = ""
    run_obj: Any = None
    run_failure_detail = ""

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
                    "text": "",
                    "agent_id": agent_id,
                    "run_id": "",
                    "error": abort,
                }

            run_obj = agent.send(prompt)
            run_id = str(getattr(run_obj, "id", None) or getattr(run_obj, "run_id", "") or "")
            stream_fn = getattr(run_obj, "stream", None) or getattr(run_obj, "messages", None)
            try:
                if callable(stream_fn):
                    for message in stream_fn():
                        abort = _abort()
                        if abort:
                            return {
                                "ok": False,
                                "text": final_text,
                                "agent_id": agent_id,
                                "run_id": run_id,
                                "error": abort,
                            }
                        mtype, st_status, st_msg = _sdk_message_fields(message)
                        if mtype == "status" and st_msg and st_status.upper() in {"ERROR", "FAILED"}:
                            run_failure_detail = st_msg
                        if mtype == "assistant":
                            piece = _assistant_text_from_message(message)
                            if piece:
                                final_text, delta, replaced = _merge_assistant_delta(final_text, piece)
                                if replaced:
                                    _emit(sink, {"type": "replace_text", "text": final_text})
                                elif delta:
                                    _emit(sink, {"type": "token", "text": delta})
            except Exception:
                pass

            result = run_obj.wait()
            status = str(getattr(result, "status", "") or "")
            result_text = str(
                getattr(result, "result", None) or getattr(result, "text", None) or ""
            )
            if result_text:
                final_text, _, _ = _merge_assistant_delta(final_text, result_text)

            abort = _abort()
            if abort:
                return {
                    "ok": False,
                    "text": final_text,
                    "agent_id": agent_id,
                    "run_id": run_id,
                    "error": abort,
                }

            if status == "error":
                detail = run_failure_detail or result_text or "未知错误"
                hint = ""
                if _USAGE_LIMIT_RE.search(detail):
                    hint = "（可能额度用尽，请检查 Cursor 账号）"
                return {
                    "ok": False,
                    "text": final_text,
                    "agent_id": agent_id,
                    "run_id": run_id,
                    "error": f"Cursor Run 失败：{detail}{hint}",
                }

            step("Cursor 本机 Agent 完成", sid="cursor-local", state="done")
            return {
                "ok": True,
                "text": final_text.strip() or "Cursor 已完成本轮本机写码。",
                "agent_id": agent_id,
                "run_id": run_id,
                "error": "",
            }
    except CursorAgentError as err:  # type: ignore[misc]
        msg = getattr(err, "message", None) or str(err)
        return {
            "ok": False,
            "text": final_text,
            "agent_id": agent_id,
            "run_id": run_id,
            "error": f"Cursor Agent 启动失败：{msg}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "text": final_text,
            "agent_id": agent_id,
            "run_id": run_id,
            "error": f"{type(exc).__name__}: {exc}",
        }
