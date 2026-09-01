"""PCB 制造领域专家对话 —— 经 LLM 答疑，供 /api/cli cmd=pcb-ask 与 mes_pcb 工具调用。"""

from __future__ import annotations

import re
from typing import Any, AsyncIterator, Dict

from .config_store import load_config
from .health import check_net, llm_ready
from .nl_engine import llm_freeform, llm_freeform_stream

# 面板 /api/chat 与 Agent 共用：识别 PCB 专业问题，避免误走 MES 查数助手
_PCB_STRONG_KEYWORDS = (
    "pcb", "印制电路", "电路板", "飞针", "aoi", "avi", "阻焊", "丝印", "字符",
    "enig", "hasl", "osp", "dfm", "ipc", "叠层", "阻抗", "线宽", "孔铜", "面铜",
    "电镀", "蚀刻", "沉铜", "除胶渣", "prepreg", "fr-4", "fr4", "化金", "表面处理",
    "开料", "压合", "盲埋", "hdi", "钢网", "锡膏", "可制造性", "离子污染",
    "四线测量", "针床", "fixture", "阻焊桥", "爆板", "层偏", "残铜", "欠腐蚀",
    "金手指", "金厚度", "tg值", "dk/df", "差分对", "参考平面",
)

PCB_SYSTEM = """你是一位在 PCB（印制电路板）行业工作超过二十年的工艺与质量顾问。
您的任务是用**专业、细致、语气温和**的中文，像耐心讲解的老师傅一样回答工程师和工艺人员的疑问。
读者读完应觉得：讲得清楚、有料、不敷衍、不冷冰冰。

## 输出要求（务必遵守）
- **只输出正式答复正文**，不要输出「思考过程」段落，也不要使用 <<<思考>>>、<<<回答>>> 或类似分隔标记
- 推理由模型侧自动完成；用户界面只会展示您的正文答复
- 禁止在正文里复述「我先想一下」「思考如下」之类元叙述

## 语气与表达（务必遵守）
- 称呼用户为「您」；开头可简短点题或表示理解（一两句即可），避免生硬直入结论
- 专业但不炫技：术语该用则用，首次出现时可括号略作白话解释
- **内容要丰满**：把原理、步骤、注意事项、常见误区讲到位；一般回答 400～900 字，复杂题可更长
- 分段清晰，适当用小标题（可用 ### 标题）或编号，不要整段文字墙
- 结尾可温和收束，或说明「若您补充××信息，还可以进一步帮您收窄原因」
- 禁止一句话带过；禁止只列名词不解释；禁止把问题推给「去查 MES」或「去平台查数据」

## 您擅长的领域
工艺流程、板材叠层、阻抗/线宽线距、钻孔与电镀、阻焊与丝印、表面处理（HASL/OSP/ENIG 等）、
DFM 可制造性、AOI/AVI/飞针/电测、缺陷根因与良率改善思路、IPC-6012/6013、IPC-A-600 等标准术语。

## 正式回答结构（按问题选用）
1. **先给结论或总览**
2. **展开说明** — 原理、流程、对比、标准要点
3. **现场经验** — 常见原因、排查顺序、易忽略细节
4. **如需更多信息** — 温和列出 2～4 条补充项

涉及缺陷时用「可能原因 → 建议怎么查 → 改善方向」；语气协作而非训诫。
涉及标准时说明适用 Class/等级，不替代正式检验裁决。"""

OFFLINE_HINT = (
    "您好，PCB 专家对话需要启用大语言模型。\n\n"
    "请在引擎配置中心配置 **DeepSeek API Key** 或本机 **Ollama 模型** 后重试。\n\n"
    "配置完成后，您可以像这样问我：\n"
    "• 四层板 50Ω 差分阻抗，设计和现场分别要控哪些点？\n"
    "• ENIG 处理后焊盘发黑，一般从哪几条线排查？\n"
    "• 飞针和 AOI 在短路检测上，产线里通常怎么分工配合？\n"
    "• IPC Class 2 和 Class 3 对孔铜厚度，主要差在哪里？"
)

FEATURE_ID = "mes-pcb"

DISABLED_HINT = (
    "PCB 制造专家功能（mes-pcb）当前已停用，因此不会提供工艺专家答疑。\n\n"
    "重新开启：\n"
    "`scripts/plugin.sh --app zr-workbuddy enable mes-pcb`\n\n"
    "约 1 秒内热加载，无需重启 DSH。"
)


def feature_enabled() -> bool:
    from . import plugins_store

    return plugins_store.is_enabled(FEATURE_ID)


_THINK_RE = re.compile(
    r"<<<\s*思考\s*>>>\s*(.*?)\s*<<<\s*回答\s*>>>\s*(.*)\s*\Z",
    re.S,
)
_MARK_STRIP = re.compile(r"<<<\s*思考\s*>>>|<<<\s*回答\s*>>>")
_ANSWER_SPLIT = re.compile(r"<<<\s*回答\s*>>>")
_THINK_ONLY = re.compile(r"<<<\s*思考\s*>>>")


def is_pcb_question(text: str) -> bool:
    """判断是否为 PCB 制造工艺/材料/检测类问题（用于 chat 路由，避免误走 MES 助手）。"""
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if "pcb" in low or "印制电路" in raw or "电路板" in raw:
        return True
    hits = sum(1 for k in _PCB_STRONG_KEYWORDS if k in low or k.upper() in raw)
    if hits >= 2:
        return True
    if hits >= 1 and re.search(r"工序|流程|怎么做|如何|为什么|区别|分工|标准|缺陷|不良", raw):
        return True
    return False


def _strip_marks(text: str) -> str:
    """去掉完整协议标记，以及流式末尾未写完的 <<<… 碎片。"""
    s = _MARK_STRIP.sub("", text or "")
    s = re.sub(r"<<<[^>]*\Z", "", s)
    return s.strip()


def split_thinking_reply(text: str, *, streaming: bool = False) -> tuple[str, str]:
    """从全文拆出 (thinking, reply)；返回值永不含协议标记。

    有 <<<思考>>>/<<<回答>>> 时按协议拆分。
    无标记：整段当回答（含 streaming），避免「无协议正文」时一直空白。
    """
    raw = text or ""
    m = _THINK_RE.search(raw.strip())
    if m:
        return _strip_marks(m.group(1)), _strip_marks(m.group(2))

    parts = _ANSWER_SPLIT.split(raw, maxsplit=1)
    if len(parts) == 2:
        left = _THINK_ONLY.sub("", parts[0])
        return _strip_marks(left), _strip_marks(parts[1])

    if _THINK_ONLY.search(raw):
        after = _THINK_ONLY.split(raw, maxsplit=1)[-1]
        return _strip_marks(after), ""

    return "", _strip_marks(raw)


def resolve_thinking_reply(
    content_acc: str,
    reasoning_acc: str,
    *,
    streaming: bool = False,
) -> tuple[str, str]:
    """合并原生 reasoning 与正文，保证思考通道单一。

    - 有原生 reasoning：thinking 固定为原生；正文里若仍带协议标记只取回答段，否则整段正文为 reply
    - 无原生：回退协议拆分 / 整段正文
    绝不在已有原生推理后再用协议思考覆盖，避免 UI「一会思考一会正文」。
    """
    proto_th, proto_rep = split_thinking_reply(content_acc, streaming=streaming)
    native = (reasoning_acc or "").strip()
    has_marks = bool(_THINK_ONLY.search(content_acc or "") or _ANSWER_SPLIT.search(content_acc or ""))

    if native:
        if has_marks:
            return native, proto_rep
        return native, _strip_marks(content_acc)

    if has_marks:
        return proto_th, proto_rep
    return "", _strip_marks(content_acc)


def _split_marked(text: str) -> tuple[str, str]:
    """非流式：从带标记的全文中拆出 (thinking, reply)。"""
    return split_thinking_reply(text, streaming=False)


def _guard_llm(cfg: dict, llm_cfg: dict) -> dict | None:
    """返回错误/离线 dict，或 None 表示可继续调 LLM。"""
    if not llm_ready(cfg):
        return {
            "ok": True,
            "reply": OFFLINE_HINT,
            "thinking": "",
            "source": "offline",
            "note": "未配置或未启用 LLM（provider=none 或缺少 Key/模型名）",
        }
    provider = (llm_cfg.get("provider") or "deepseek").lower()
    if provider == "deepseek" and not check_net():
        return {
            "ok": False,
            "detail": "DeepSeek API 需要外网；当前网络不可用，可改用本机 Ollama。",
        }
    return None


async def pcb_ask(text: str) -> dict:
    """PCB 领域专家问答（非流式，含 thinking 字段）。须 mes-pcb 已启用。"""
    q = (text or "").strip()
    if not q:
        return {"ok": False, "detail": "问题不能为空"}

    if not feature_enabled():
        return {
            "ok": True,
            "reply": DISABLED_HINT,
            "thinking": "",
            "source": "disabled",
            "domain": "pcb",
            "note": "mes-pcb 未启用",
        }

    cfg = load_config()
    llm_cfg = cfg.get("deepseek") or {}
    blocked = _guard_llm(cfg, llm_cfg)
    if blocked is not None:
        return blocked

    raw = await llm_freeform(
        PCB_SYSTEM,
        q,
        llm_cfg,
        max_tokens=4096,
        timeout=120,
        temperature=0.35,
    )
    if not raw:
        return {
            "ok": False,
            "detail": "LLM 调用失败，请检查 API Key、模型名或 Ollama 服务是否可用。",
        }
    thinking, reply = _split_marked(raw)
    return {
        "ok": True,
        "reply": reply or raw,
        "thinking": thinking,
        "source": "llm",
        "domain": "pcb",
    }


async def pcb_ask_stream(text: str) -> AsyncIterator[Dict[str, Any]]:
    """PCB 专家流式问答。事件：status / thinking / reply / error / done(+汇总)。"""
    q = (text or "").strip()
    if not q:
        yield {"type": "error", "detail": "问题不能为空"}
        return

    if not feature_enabled():
        yield {"type": "reply", "delta": DISABLED_HINT}
        yield {
            "type": "done",
            "ok": True,
            "reply": DISABLED_HINT,
            "thinking": "",
            "source": "disabled",
            "domain": "pcb",
            "note": "mes-pcb 未启用",
        }
        return

    cfg = load_config()
    llm_cfg = cfg.get("deepseek") or {}
    blocked = _guard_llm(cfg, llm_cfg)
    if blocked is not None:
        if blocked.get("ok"):
            if blocked.get("thinking"):
                yield {"type": "thinking", "delta": blocked["thinking"]}
            yield {"type": "reply", "delta": blocked.get("reply") or ""}
            yield {
                "type": "done",
                "ok": True,
                "reply": blocked.get("reply") or "",
                "thinking": blocked.get("thinking") or "",
                "source": blocked.get("source") or "offline",
                "domain": "pcb",
                "note": blocked.get("note"),
            }
        else:
            yield {"type": "error", "detail": blocked.get("detail") or "失败"}
        return

    yield {"type": "status", "detail": "正在整理思路…"}
    # 全文累积后再拆分：标记常被拆到多个 token；推送绝对 text，避免前端 delta 错位
    # 思考通道优先原生 reasoning；正文协议标记仅作兼容清理，不得覆盖已推送的原生思考
    content_acc = ""
    reasoning_acc = ""
    last_thinking = ""
    last_reply = ""
    async for ev in llm_freeform_stream(
        PCB_SYSTEM,
        q,
        llm_cfg,
        max_tokens=4096,
        timeout=120,
        temperature=0.35,
    ):
        t = ev.get("type")
        if t == "reasoning":
            delta = ev.get("delta") or ""
            if delta:
                reasoning_acc += delta
                thinking, _ = resolve_thinking_reply(content_acc, reasoning_acc, streaming=True)
                if thinking != last_thinking:
                    last_thinking = thinking
                    yield {"type": "thinking", "text": last_thinking}
        elif t == "content":
            content_acc += ev.get("delta") or ""
            thinking, reply = resolve_thinking_reply(content_acc, reasoning_acc, streaming=True)
            if thinking != last_thinking:
                last_thinking = thinking
                yield {"type": "thinking", "text": thinking}
            if reply != last_reply:
                last_reply = reply
                yield {"type": "reply", "text": reply}
        elif t == "error":
            yield ev
            return
        elif t == "done":
            thinking, reply = resolve_thinking_reply(content_acc, reasoning_acc, streaming=False)
            if thinking != last_thinking:
                yield {"type": "thinking", "text": thinking}
            if reply != last_reply:
                yield {"type": "reply", "text": reply}
            yield {
                "type": "done",
                "ok": True,
                "reply": reply,
                "thinking": thinking,
                "source": "llm",
                "domain": "pcb",
            }


def chat_response(out: dict) -> dict:
    """将 pcb_ask 结果转为与 /api/chat、mes_ask 一致的响应形状。"""
    if not out.get("ok"):
        return {"ok": False, "detail": out.get("detail") or "PCB 问答失败"}
    return {
        "ok": True,
        "reply": out.get("reply") or "",
        "thinking": out.get("thinking") or "",
        "chart": None,
        "table": None,
        "note": out.get("note"),
        "source": out.get("source") or "llm",
        "data_source": "pcb_expert",
        "intent": {
            "type": "pcb_chat",
            "metric": "",
            "dim": None,
            "chart": None,
        },
    }
