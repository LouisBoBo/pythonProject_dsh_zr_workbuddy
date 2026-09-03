"""自然语言 → 查询意图（中文规则引擎）。

离线可用。DeepSeek 结构化解析作为可选增强（网络可用时启用，见 main.chat）。

输出 intent:
{
  metric, dim, type, chart, direction,
  date_from, date_to, range_desc, granularity, filters, raw
}
"""

import re
from datetime import date, timedelta

METRIC_KEYWORDS = [
    ("oee", ["oee", "综合效率"]),
    ("defect_rate", ["不良率"]),
    ("yield", ["良率", "合格率"]),
    ("defect_share", ["缺陷", "帕累托", "不良原因", "不良分布", "不良构成"]),
    ("downtime", ["停机", "故障", "宕机"]),
    ("achievement", ["达成", "完成率"]),
    ("utilization", ["利用率", "稼动率"]),
    ("in_progress_orders", [
        "正在生产", "在生产", "生产中", "在制", "再制", "在制品", "再制品",
        "进行中", "在产", "未完工", "生产中的工单", "在制工单", "再制工单",
        "wip",
    ]),
    ("completed_orders", ["完工工单", "完成工单", "完工工单数", "完工数", "完工数量", "已完成工单"]),
    ("output", ["产量", "产出", "生产", "数量"]),
]

DIM_KEYWORDS = [
    ("product", ["产品", "型号", "物料"]),
    ("line", ["产线", "线别", "车间"]),
    ("shift", ["班次", "白班", "夜班"]),
    ("equipment", ["设备", "机台"]),
    ("process", ["工序", "工艺"]),
]

METRIC_NAMES = {
    "oee": "OEE", "yield": "良率", "defect_rate": "不良率", "output": "产量",
    "planned": "计划产量", "achievement": "达成率", "downtime": "停机时长",
    "utilization": "设备利用率", "defect_share": "缺陷占比", "completed_orders": "完工工单数",
    "in_progress_orders": "在制工单数", "work_orders_total": "工单总数",
}
DIM_NAMES = {"line": "产线", "product": "产品", "shift": "班次", "equipment": "设备", "process": "工序"}


def _parse_time(t: str, today: date) -> tuple:
    """返回 (date_from, date_to, range_desc)。"""
    if "今天" in t or "今日" in t or "当天" in t:
        return today, today, "今天"
    if "昨天" in t or "昨日" in t:
        y = today - timedelta(days=1)
        return y, y, "昨天"
    if "本周" in t or "这周" in t:
        monday = today - timedelta(days=today.weekday())
        return monday, today, "本周"
    if "上周" in t:
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(days=7), monday - timedelta(days=1), "上周"
    if "本月" in t or "这个月" in t:
        return today.replace(day=1), today, "本月"
    if "上月" in t or "上个月" in t:
        first = today.replace(day=1)
        last_prev = first - timedelta(days=1)
        return last_prev.replace(day=1), last_prev, "上月"

    # 绝对日期：8月30号 / 8月30日 / 8/30
    m = re.search(r"(\d{1,2})[月/](\d{1,2})[号日]?", t)
    if m:
        try:
            d = today.replace(month=int(m.group(1)), day=int(m.group(2)))
        except ValueError:
            d = today
        return d, d, f"{m.group(1)}月{m.group(2)}号"

    m = re.search(r"(?:最近|近|过去)?\s*(\d+)\s*(天|日|周|个月|月|星期)", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        days = n * 7 if unit == "周" or unit == "星期" else n * 30 if "月" in unit else n
        return today - timedelta(days=days - 1), today, f"最近{n}{'周' if unit in ('周', '星期') else '个月' if '月' in unit else '天'}"
    return today - timedelta(days=29), today, "最近30天"


def _extract_filters(t: str, dim: str) -> dict:
    filters = {}
    m = re.search(r"\bL\s?(\d)\b", t)
    if m:
        filters["line"] = f"L{m.group(1)}"
    m = re.search(r"\b([ABC])-(\d{2})\b", t)
    if m:
        filters["product"] = f"{m.group(1)}-{m.group(2)}"
    if "白班" in t:
        filters["shift"] = "白班"
    elif "夜班" in t:
        filters["shift"] = "夜班"
    # 若筛选值恰好是维度本身，则去掉维度分组（转为该对象的趋势/单值）
    for k, v in list(filters.items()):
        if dim == k:
            dim = None
    return filters, dim


def parse_question(text: str) -> dict:
    t = text.strip()
    tl = t.lower()
    today = date.today()

    # 指标（记录是否命中，未命中则视为未识别意图）
    metric = "output"
    metric_hit = False
    for name, kws in METRIC_KEYWORDS:
        if any(k in tl if k.isascii() else k in t for k in kws):
            metric = name
            metric_hit = True
            break

    # 通用"工单 + 多少个/几个" → 工单总数（无状态限定；在制/完工等已在上面命中）
    if not metric_hit and "工单" in t and any(k in t for k in ("多少", "几个", "多少个", "数量", "工单数", "工单数量")):
        metric = "work_orders_total"
        metric_hit = True

    # 维度
    dim = None
    for name, kws in DIM_KEYWORDS:
        if any(k in t for k in kws):
            dim = name
            break

    # 时间
    date_from, date_to, range_desc = _parse_time(t, today)

    # 类型与图表
    ask_count = any(k in t for k in ("多少", "几个", "多少个", "有多少", "数量是多少"))
    qtype, chart = "single", "bar"
    if any(k in t for k in ("原因", "为什么", "为啥", "过低", "下降", "异常", "是什么导致", "怎么回事", "因为什么")):
        qtype, chart = "analysis", "bar"
    elif any(k in t for k in ["趋势", "走势", "变化", "每天", "每日", "逐日", "环比"]):
        qtype, chart = "trend", "line"
    elif any(k in t for k in ["占比", "比例", "分布", "构成"]):
        qtype, chart = "share", "pie"
        if metric not in ("defect_share", "yield", "defect_rate"):
            metric = "defect_share"
    elif any(k in t for k in ["对比", "比较"]):
        qtype, chart = "compare", "bar"
        if not dim:
            dim = "line"
    elif "top" in tl or "排名" in t or "排行" in t or "前" in t:
        qtype, chart = "ranking", "bar"
        if not dim:
            dim = "product"
    elif dim:
        qtype, chart = "compare", "bar"
    elif ask_count or metric in ("in_progress_orders", "completed_orders", "work_orders_total"):
        qtype, chart = "single", "bar"
    else:
        qtype, chart = "trend", "line"

    # 特殊意图只在"非数据问题"时生效（避免"功能测试良率"误判为帮助等）
    is_data_q = metric_hit or bool(dim)
    if not is_data_q:
        if any(k in t for k in ("你好", "您好", "嗨", "哈喽", "早上好", "下午好", "晚上好", "在吗", "hello", "hi", "hey")):
            return _special("greeting", text)
        if any(k in t for k in ("谢谢", "感谢", "多谢", "辛苦你", "thanks", "thank")):
            return _special("thanks", text)
        if any(k in tl for k in ("help", "帮助", "能做什么", "你能干嘛", "你会什么", "有什么功能",
                                 "怎么使用", "如何使用", "功能列表", "功能介绍", "怎么用")):
            return _special("help", text)
        return _special("unknown", text)

    direction = "desc"
    if qtype == "ranking":
        if any(k in t for k in ["最低", "最差", "最少", "最小"]):
            direction = "asc"
        elif any(k in t for k in ["最高", "最好", "最多", "最大"]):
            direction = "desc"

    filters, dim = _extract_filters(t, dim)

    granularity = "week" if (date_to - date_from).days > 60 else "day"

    return {
        "metric": metric, "dim": dim, "type": qtype, "chart": chart,
        "direction": direction, "date_from": date_from, "date_to": date_to,
        "range_desc": range_desc, "granularity": granularity,
        "filters": filters, "raw": text,
        "metric_name": METRIC_NAMES.get(metric, metric),
        "dim_name": DIM_NAMES.get(dim, "") if dim else "",
    }


def _special(kind: str, text: str) -> dict:
    """问候 / 感谢 / 帮助 / 未识别 等非数据类意图。"""
    return {
        "metric": "", "dim": None, "type": kind, "chart": None,
        "direction": "desc", "date_from": None, "date_to": None,
        "range_desc": "", "granularity": "day",
        "filters": {}, "raw": text,
        "metric_name": "", "dim_name": "",
    }


# ---------------- LLM 意图理解（DeepSeek API / Ollama 本地） ----------------

# ---------------- LLM 全场景理解（DeepSeek API / Ollama 本地） ----------------

METRIC_ALLOWED = set(METRIC_NAMES) | {"planned"}
DIM_ALLOWED = set(DIM_NAMES)
TYPE_ALLOWED = {"trend", "compare", "ranking", "share", "single", "analysis"}
CHART_ALLOWED = {"line", "bar", "pie"}

METRICS_SUMMARY = (
    "完工工单数/在制工单数/工单总数/产量/计划产量/达成率/良率/不良率/缺陷占比/OEE/停机(告警次数)/设备利用率；"
    "维度：产线/产品/班次/设备/工序；类型：趋势/对比/排名/占比/单值/原因分析"
)

LLM_CHAT_SYSTEM = """你是「ZR-WorkBuddy」工作助手（项目 DSH-ZR-WorkBuddy），可协助查询与解读生产相关数据（可来自 MES/ERP 等系统）。
你**必须理解用户的任何输入**，然后按下述规则回应（只输出一个 JSON 对象，不要任何其他文字）。

【规则一：用户是在查数据/分析数据】输出：{"kind":"query","intent":{...}}
intent 字段说明：
- metric: completed_orders | in_progress_orders | work_orders_total | oee | yield | defect_rate |
         defect_share | output | planned | achievement | downtime | utilization
- dim: line | product | shift | equipment | process | null
- type: trend | compare | ranking | share | single | analysis
- chart: line | bar | pie
- direction: desc | asc
- days: 今天=1，昨天=1，最近N天=N，本周≈7，本月≈30；默认30
- date: 可选；用户明确指定某一天时填 YYYY-MM-DD（如 8月30号→2026-08-30），填了忽略 days
- filters: 按问题里的具体对象，如 {"line":"L1"} {"product":"A-01"} {"shift":"白班"} {"process":"贴片"}
指标含义（务必按用户限定的状态选对 metric，不要轻易落到 work_orders_total）：
- completed_orders：完工/已完成/做完了的工单数量
- in_progress_orders：正在生产/生产中/在制/在制品/再制品/再制/WIP/进行中/未完工的工单数量
  （「再制品」与「在制品」同义，均指在制 WIP，不是工单总数）
- work_orders_total：仅当用户问「工单一共多少/工单总数/全部工单」且未限定状态时使用
- oee 设备综合效率；yield 良率；defect_rate 不良率；defect_share 缺陷占比/分布
- output 产量；planned 计划产量；achievement 达成率
- downtime 停机/故障（本平台展示为告警次数）；utilization 设备利用率
类型含义：trend 趋势/走势/每天；compare 对比/比较/各...；ranking 排名/TOP/最高/最低；
         share 占比/分布/构成；single 单值（「有多少个/几个」类计数题用 single）；
         analysis 原因分析（问题含"分析原因/为什么…低/为什么…下降/怎么回事"）
示例：
- 「今日再制品工单有多少个」→ {"kind":"query","intent":{"metric":"in_progress_orders","dim":null,"type":"single","chart":"bar","days":1,"filters":{}}}
- 「今天正在生产的工单有多少个」→ metric=in_progress_orders, type=single, days=1
- 「今天完工工单数量」→ metric=completed_orders, type=single, days=1
- 「工单一共多少个」→ metric=work_orders_total, type=single, days=1

【规则二：用户要改代码 / 做界面 / 开发菜单页面等】输出：{"kind":"code_dev","reply":"简短确认这是写码需求即可"}
当用户提到开发界面、改菜单、写码、改前端/后端、实现某某页面等（不是查产量/良率）：
- 即使你不确定能否立刻改代码，也必须输出 kind=code_dev，**禁止**说「平台不支持界面开发/代码修改」。
- reply 可很短，系统会接管后续引导（路径、配置中心）。

【规则二点五：用户要部署 / 上线 / 发到预发】输出：{"kind":"code_deploy","reply":"简短确认这是部署需求即可"}
当用户提到部署上线、发到预发、增量部署、SSH 同步到测试机等（不是查「部署工单」类 MES 业务）：
- 必须输出 kind=code_deploy，**禁止**说「暂不支持部署上线」。
- 系统会弹出按插件勾选确认卡，由人确认后本机 SSH 同步；模型不会自己执行 SSH。

【规则三：其他任何输入】输出：{"kind":"chat","reply":"..."}
包括：问候/感谢/闲聊；问概念（如"OEE是什么""良率怎么算"）；问"你能做什么"；问平台怎么用；
以及用户要求但平台做不了的事（预测未来产量、导出Excel、修改/写入 MES 业务数据、接入其他系统、实时推送等）
——这类必须**如实说明目前不支持/尚未接入**，语气友善，并给出可以怎么做，2~4 句，中文，简洁。

【平台能力边界（用于如实回答）】
支持：查询 MES 生产数据并自动出图与洞察（__METRICS_SUMMARY__）；单日/区间原因分析；
__CODE_DEV_BOUNDARY__
__CODE_DEPLOY_BOUNDARY__
暂不支持：预测/机器学习、数据导出、向 MES **写入业务数据**、跨系统查询、实时告警推送。

【当前环境】__CONTEXT__
"""


def _extract_json(content: str):
    import json as _json
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return _json.loads(content[start:end + 1])
    except Exception:
        return None


def _intent_from_obj(obj: dict, text: str) -> dict | None:
    """把 LLM 返回的 intent 对象转成意图字典（白名单校验）。"""
    if not isinstance(obj, dict):
        return None
    metric = obj.get("metric") or ""
    if metric not in METRIC_ALLOWED:
        return None
    dim = obj.get("dim") or None
    if dim not in DIM_ALLOWED and dim is not None:
        return None
    qtype = obj.get("type") or "single"
    if qtype not in TYPE_ALLOWED:
        return None
    chart = obj.get("chart") or "bar"
    if chart not in CHART_ALLOWED:
        return None
    try:
        days = max(1, min(int(obj.get("days") or 30), 3650))
    except Exception:
        days = 30
    today = date.today()
    filters = obj.get("filters") or {}
    if not isinstance(filters, dict):
        filters = {}
    date_override = obj.get("date")
    range_desc = f"最近{days}天"
    if isinstance(date_override, str) and len(date_override) >= 10:
        try:
            d = date.fromisoformat(date_override.strip()[:10])
            date_from = date_to = d
            range_desc = d.isoformat()
            days = 1
        except ValueError:
            date_from = today - timedelta(days=days - 1)
            date_to = today
    else:
        # 原文含「今天/今日/昨天…」时优先用规则解析，避免 days=1 变成「最近1天」
        time_keys = ("今天", "今日", "当天", "昨天", "昨日", "本周", "这周", "上周",
                     "本月", "这个月", "上月", "上个月")
        if any(k in text for k in time_keys):
            date_from, date_to, range_desc = _parse_time(text, today)
            days = (date_to - date_from).days + 1
        else:
            date_from = today - timedelta(days=days - 1)
            date_to = today
    return {
        "metric": metric, "dim": dim, "type": qtype, "chart": chart,
        "direction": "asc" if obj.get("direction") == "asc" else "desc",
        "date_from": date_from, "date_to": date_to,
        "range_desc": range_desc, "granularity": "week" if days > 60 else "day",
        "filters": filters, "raw": text,
        "metric_name": METRIC_NAMES.get(metric, metric),
        "dim_name": DIM_NAMES.get(dim, "") if dim else "",
    }


def _parse_llm_response(content: str, text: str) -> dict | None:
    """LLM 输出文本 → 意图（旧接口，兼容测试）。"""
    obj = _extract_json(content)
    if obj is None:
        return None
    return _intent_from_obj(obj, text)


async def _llm_call(
    messages: list,
    llm_cfg: dict,
    timeout: float = 12,
    max_tokens: int = 500,
    temperature: float = 0,
    *,
    no_cache: bool = False,
) -> str | None:
    """调用 LLM 并返回回复文本；失败返回 None（含模型名兜底重试）。"""
    import httpx
    provider = (llm_cfg.get("provider") or "deepseek").lower()
    base = (llm_cfg.get("base_url") or "").strip().rstrip("/")
    model = (llm_cfg.get("model") or "").strip()
    if provider == "ollama":
        if not base:
            base = "http://127.0.0.1:11434"
        v1 = base + "/v1" if not base.endswith("/v1") else base
        headers = {}
        if not model:
            return None
    else:
        if not base:
            base = "https://api.deepseek.com"
        v1 = base + "/v1" if not base.endswith("/v1") else base
        headers = {"Authorization": f"Bearer {(llm_cfg.get('api_key') or '').strip()}"}
        if not llm_cfg.get("api_key"):
            return None
    if no_cache:
        headers = {
            **headers,
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
        }

    async def _do(m: str):
        payload = {
            "model": m,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # DeepSeek V4 默认 thinking 会吃光 max_tokens；仅对该厂商关闭。
        # Ollama 等兼容网关可能不认 thinking 字段，勿无条件附带。
        if no_cache and provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(v1 + "/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            reasoning = (
                msg.get("reasoning_content")
                or msg.get("reasoning")
                or msg.get("thinking")
                or ""
            )
            reasoning = str(reasoning).strip()
            if content:
                return content
            if reasoning:
                return reasoning
            return ""

    try:
        out = await _do(model or "deepseek-chat")
        return out if out else None
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("llm_call failed provider=%s model=%s: %s", provider, model, e)
        if provider != "ollama" and model and model != "deepseek-chat":
            try:
                out = await _do("deepseek-chat")
                return out if out else None
            except Exception as e2:
                logging.getLogger(__name__).warning("llm_call fallback failed: %s", e2)
                return None
        return None


async def llm_freeform(
    system: str,
    user: str,
    llm_cfg: dict,
    *,
    max_tokens: int = 2000,
    timeout: float = 60,
    temperature: float = 0.3,
    no_cache: bool = False,
) -> str | None:
    """自由对话式 LLM 调用（非 JSON 意图解析）。"""
    return await _llm_call(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        llm_cfg,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
        no_cache=no_cache,
    )


async def llm_freeform_stream(
    system: str,
    user: str,
    llm_cfg: dict,
    *,
    max_tokens: int = 4096,
    timeout: float = 120,
    temperature: float = 0.35,
):
    """流式自由对话。只吐原始增量，切分由调用方做全文解析（避免标记被拆碎漏出）。

    yield dict：
    - {"type":"reasoning","delta":"..."}  原生推理（若有）
    - {"type":"content","delta":"..."}    模型正文增量（可能含协议标记）
    - {"type":"error","detail":"..."}
    - {"type":"done"}
    """
    import httpx
    import json as _json

    provider = (llm_cfg.get("provider") or "deepseek").lower()
    base = (llm_cfg.get("base_url") or "").strip().rstrip("/")
    model = (llm_cfg.get("model") or "").strip()
    if provider == "ollama":
        if not base:
            base = "http://127.0.0.1:11434"
        v1 = base + "/v1" if not base.endswith("/v1") else base
        headers = {"Accept": "text/event-stream"}
        if not model:
            yield {"type": "error", "detail": "Ollama 未配置模型名"}
            return
    else:
        if not base:
            base = "https://api.deepseek.com"
        v1 = base + "/v1" if not base.endswith("/v1") else base
        key = (llm_cfg.get("api_key") or "").strip()
        if not key:
            yield {"type": "error", "detail": "DeepSeek 未配置 API Key"}
            return
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }

    payload = {
        "model": model or "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15.0)) as client:
            async with client.stream(
                "POST",
                v1 + "/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:300]
                    yield {"type": "error", "detail": f"LLM HTTP {resp.status_code}: {body}"}
                    return
                async for line in resp.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = _json.loads(data)
                    except Exception:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    content = delta.get("content")
                    if reasoning:
                        yield {"type": "reasoning", "delta": reasoning}
                    if content:
                        yield {"type": "content", "delta": content}
        yield {"type": "done"}
    except Exception as e:
        yield {"type": "error", "detail": f"{type(e).__name__}: {e}"}


async def llm_chat(text: str, llm_cfg: dict, context: str) -> dict | None:
    """大模型理解任何输入 → 返回：
    - {"kind":"query","intent":{...}}  查数据
    - {"kind":"code_dev","reply":"..."} 写码意图（由调用方接管）
    - {"kind":"code_deploy","reply":"..."} 部署意图（由调用方接管）
    - {"kind":"chat","reply":"..."}    对话/能力边界
    - None                              调用失败（调用方回退规则引擎）
    """
    from . import plugins_store
    from .code_deploy.ops import FEATURE_ID as CODE_DEPLOY_FEATURE
    from .code_dev.ops import FEATURE_ID as CODE_DEV_FEATURE

    if plugins_store.is_enabled(CODE_DEV_FEATURE):
        code_boundary = (
            "本机 Cursor 写码（改工程界面/功能）：用户提出开发/改界面/写码时输出 kind=code_dev，"
            "不要说不支持代码修改。"
        )
    else:
        code_boundary = "本机写码功能当前未启用；若用户要开发界面，kind=chat 并说明可到配置中心开启写码车道。"

    if plugins_store.is_enabled(CODE_DEPLOY_FEATURE):
        deploy_boundary = (
            "按插件增量部署（本机 SSH/rsync 到预发）：用户说部署上线/发到预发时输出 kind=code_deploy，"
            "禁止说暂不支持部署；人确认后才会同步。"
        )
    else:
        deploy_boundary = (
            "自动化部署功能当前未启用；若用户要部署上线，kind=chat 并说明可到配置中心开启自动化部署、"
            "并启用功能插件 code-deploy。"
        )

    system = (
        LLM_CHAT_SYSTEM.replace("__METRICS_SUMMARY__", METRICS_SUMMARY)
        .replace("__CONTEXT__", context)
        .replace("__CODE_DEV_BOUNDARY__", code_boundary)
        .replace("__CODE_DEPLOY_BOUNDARY__", deploy_boundary)
    )
    content = await _llm_call([
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ], llm_cfg)
    if not content:
        return None
    obj = _extract_json(content)
    if not isinstance(obj, dict):
        return None
    kind = obj.get("kind")
    if kind == "query":
        intent = _intent_from_obj(obj.get("intent") or {}, text)
        if intent:
            return {"kind": "query", "intent": intent}
        return None
    if kind == "code_dev":
        return {"kind": "code_dev", "reply": str(obj.get("reply") or "").strip()}
    if kind == "code_deploy":
        return {"kind": "code_deploy", "reply": str(obj.get("reply") or "").strip()}
    if kind == "chat":
        reply = str(obj.get("reply") or "").strip()
        if reply:
            return {"kind": "chat", "reply": reply}
    return None
