"""MES 实时分析：自然语言意图 → 调用 ERP 分析接口 → 图表 / 表格 / 洞察。

支持的指标：
- oee            → /api/device/oee（整体）
- output/planned/achievement → /api/reports/daily-output（按产线/产品/日期聚合）
- yield/defect_rate → /api/quality/kpi + /api/quality/trend + daily-output
- defect_share   → /api/quality/defect-distribution
- downtime       → /api/device/alarms/trend（告警次数，非时长）
"""

import pandas as pd

from .analyzer import fmt, render_bar, render_line, render_line_multi, render_pie
from .mes_client import MesError, api_get, fetch_daily_output


def _empty(range_desc: str) -> dict:
    return {"reply": f"MES 在{range_desc}范围内暂无数据，试试其他时间范围。",
            "chart": None, "table": None, "title": "", "note": None}


async def analyze_mes(intent: dict, cfg_mes: dict) -> dict:
    if intent.get("type") == "analysis":
        return await _analyze_causes(intent, cfg_mes)
    metric = intent["metric"]
    if metric == "oee":
        return await _oee(intent, cfg_mes)
    if metric in ("output", "planned", "achievement"):
        return await _output(intent, cfg_mes)
    if metric in ("yield", "defect_rate"):
        return await _quality_rate(intent, cfg_mes)
    if metric == "defect_share":
        return await _defect_share(intent, cfg_mes)
    if metric == "downtime":
        return await _alarms(intent, cfg_mes)
    if metric == "completed_orders":
        return await _completed_orders(intent, cfg_mes)
    if metric == "in_progress_orders":
        return await _in_progress_orders(intent, cfg_mes)
    if metric == "work_orders_total":
        return await _work_orders_total(intent, cfg_mes)
    raise MesError(f"MES 暂不支持指标 {metric}")


STATUS_LABELS = {"pending": "待生产", "in_progress": "生产中", "completed": "已完成",
                 "closed": "已关闭", "cancelled": "已取消", "draft": "草稿"}


async def _fetch_work_orders(cfg_mes: dict, status: str = "", line: str = "") -> list:
    """分页拉取工单列表（可按状态/产线过滤）。"""
    rows, page = [], 1
    while True:
        params = {"page": page, "page_size": 100}
        if status:
            params["status"] = status
        if line:
            params["production_line"] = line
        d = await api_get(cfg_mes, "/api/work-orders", params)
        items = d.get("items") or []
        rows.extend(items)
        total = d.get("total")
        if len(items) < 100 or (total and len(rows) >= int(total)) or page >= 20:
            break
        page += 1
    return rows


async def _in_progress_orders(intent: dict, cfg_mes: dict) -> dict:
    """在制工单数：status=in_progress（当前正在生产的工单）。"""
    line_filter = (intent.get("filters") or {}).get("line", "")
    rows = await _fetch_work_orders(cfg_mes, status="in_progress", line=line_filter)
    if not rows:
        return _empty(intent["range_desc"])
    df = pd.DataFrame(rows)
    dim = intent["dim"]
    dname = intent.get("dim_name") or ""
    group_col = {"line": "production_line", "product": "product_name"}.get(dim, "production_line")
    g = df.groupby(group_col).size().sort_values(ascending=False)
    labels, values = g.index.tolist()[:6], g.tolist()[:6]
    title = f"{intent['range_desc']}各{dname or '产线'}在制工单数（MES）"
    detail = "、" .join(f"{l} {v} 个" for l, v in zip(labels, values))
    reply = f"📊 {title}：**{len(df)} 个**正在生产中" + (f"（{detail}）。" if detail else "。")
    return {"reply": reply, "chart": render_bar(title, labels, values, "in_progress_orders"),
            "table": [{"label": l, "value": f"{v} 个", "extra": ""} for l, v in zip(labels, values)],
            "title": title, "note": "按工单当前状态（in_progress）统计"}


async def _work_orders_total(intent: dict, cfg_mes: dict) -> dict:
    """工单总数：不按状态过滤，按状态分组展示。"""
    line_filter = (intent.get("filters") or {}).get("line", "")
    rows = await _fetch_work_orders(cfg_mes, line=line_filter)
    if not rows:
        return _empty(intent["range_desc"])
    df = pd.DataFrame(rows)
    g = df.groupby("status").size().sort_values(ascending=False)
    labels = [STATUS_LABELS.get(s, s) for s in g.index]
    values = g.tolist()
    title = f"工单总数（{intent['range_desc']}）"
    reply = f"📊 {title}：共 **{len(df)}** 个，" + "、".join(
        f"{l} {v}" for l, v in zip(labels, values)) + "。"
    return {"reply": reply, "chart": render_bar(title, labels, values, "work_orders_total"),
            "table": [{"label": l, "value": f"{v} 个", "extra": ""} for l, v in zip(labels, values)],
            "title": title, "note": None}


async def _completed_orders(intent: dict, cfg_mes: dict) -> dict:
    """完工工单数量：分页拉取 status=completed 的工单，按实际完成时间过滤。"""
    from_, to_ = intent["date_from"], intent["date_to"]
    line_filter = (intent.get("filters") or {}).get("line", "")
    rows = await _fetch_work_orders(cfg_mes, status="completed", line=line_filter)
    if not rows:
        return _empty(intent["range_desc"])
    df = pd.DataFrame(rows)
    df["_d"] = df["actual_end_time"].map(lambda v: str(v)[:10] if v else None)
    df = df[(df["_d"] >= from_.isoformat()) & (df["_d"] <= to_.isoformat())]
    if df.empty:
        return _empty(intent["range_desc"])

    dim = intent["dim"]
    qtype = intent["type"]
    dname = intent.get("dim_name") or ""
    days = (to_ - from_).days
    total_n = int(len(df))

    # 趋势（时间跨度 > 2 天且无维度）
    if qtype == "trend" and days > 2 and not dim:
        g = df.groupby("_d").size().sort_index()
        labels = [d[5:] for d in g.index]
        values = g.tolist()
        title = f"{intent['range_desc']}完工工单数趋势（MES）"
        reply = (f"📈 {title}：共 **{total_n}** 张，"
                 f"最高 {max(values)} 张（{labels[values.index(max(values))]}），"
                 f"最低 {min(values)} 张（{labels[values.index(min(values))]}）。")
        return {"reply": reply, "chart": render_line(title, labels, values, "completed_orders"),
                "table": None, "title": title, "note": None}

    # 汇总 + 按维度（产线/产品）分组
    group_col = {"line": "production_line", "product": "product_name"}.get(dim, "production_line")
    g = df.groupby(group_col).size().sort_values(ascending=False)
    labels = g.index.tolist()[:6]
    values = g.tolist()[:6]
    title = f"{intent['range_desc']}各{dname or '产线'}完工工单数（MES）"
    reply = f"📊 {title}：共 **{total_n}** 张，" + "、".join(
        f"{l} {v} 张" for l, v in zip(labels, values)) + "。"
    if labels:
        reply += f" 最多为 **{labels[0]}（{values[0]} 张）**"
    return {"reply": reply, "chart": render_bar(title, labels, values, "completed_orders"),
            "table": [{"label": l, "value": f"{v} 张", "extra": ""} for l, v in zip(labels, values)],
            "title": title, "note": None}


async def _oee(intent: dict, cfg_mes: dict) -> dict:
    d = await api_get(cfg_mes, "/api/device/oee")
    avail = float(d.get("availability", 0) or 0)
    perf = float(d.get("performance", 0) or 0)
    quality = float(d.get("quality", 0) or 0)
    oee = float(d.get("oee", 0) or 0)
    title = f"MES 设备综合效率 OEE 分解（{intent['range_desc']}）"
    reply = (f"📊 MES 实时设备综合效率（OEE）：**{oee:.1f}%**\n"
             f"可用率 {avail:.1f}% × 性能率 {perf:.1f}% × 良率 {quality:.1f}%")
    # MES 返回百分数值，转小数供 fmt 统一格式化
    chart = render_bar(title, ["可用率", "性能率", "良率", "OEE"],
                       [avail / 100, perf / 100, quality / 100, oee / 100], "oee")
    table = [{"label": k, "value": f"{float(v or 0):.1f}%", "extra": ""}
             for k, v in [("可用率", avail), ("性能率", perf), ("良率", quality), ("综合效率 OEE", oee)]]
    note = "MES 仅提供整体 OEE（无产线维度）；如需各产线对比，可在 ERP 增加按产线 OEE 接口" \
        if intent.get("dim") else None
    return {"reply": reply, "chart": chart, "table": table, "title": title, "note": note}


async def _output(intent: dict, cfg_mes: dict) -> dict:
    from_, to_ = intent["date_from"].isoformat(), intent["date_to"].isoformat()
    line_filter = (intent.get("filters") or {}).get("line", "")
    rows = await fetch_daily_output(cfg_mes, date_from=from_, date_to=to_, line=line_filter)
    if not rows:
        return _empty(intent["range_desc"])
    df = pd.DataFrame(rows)
    metric = intent["metric"]
    dim = intent["dim"]
    qtype = intent["type"]
    mname = intent.get("metric_name") or metric
    dname = intent.get("dim_name") or ""

    if metric == "planned":
        df["_v"] = df["plan_qty"].astype(float)
    elif metric == "achievement":
        df["_v"] = (df["actual_qty"].astype(float) / df["plan_qty"].astype(float).replace(0, pd.NA)).fillna(0)
    else:
        df["_v"] = df["actual_qty"].astype(float)

    if dim in ("shift", "equipment"):
        raise MesError(f"MES 暂不支持按{dname}维度查询产量")

    # ---- 趋势 ----
    if qtype == "trend" and not (dim and dim in (intent.get("filters") or {})):
        if dim:
            pivot = df.pivot_table(index="report_date", columns={"line": "production_line", "product": "product_name"}[dim],
                                   values="_v", aggfunc="sum").fillna(0).sort_index()
            labels = [d[5:] for d in pivot.index]
            series = [{"name": c, "data": pivot[c].tolist()} for c in pivot.columns]
            title = f"{intent['range_desc']}各{dname}{mname}趋势（MES）"
            reply = f"📈 {title}：共 {len(pivot)} 天数据。"
            if len(labels) <= 1:  # 单点不画折线，展示分组柱状
                latest = pivot.iloc[-1].sort_values(ascending=False)
                title2 = f"{intent['range_desc']}各{dname}{mname}（MES）"
                reply2 = f"📊 {title2}：" + "、".join(
                    f"{k} {fmt(v, metric)}" for k, v in latest.items()) + "。"
                return {"reply": reply2,
                        "chart": render_bar(title2, latest.index.tolist(), latest.tolist(), metric),
                        "table": [{"label": k, "value": fmt(v, metric), "extra": ""}
                                  for k, v in latest.items()],
                        "title": title2, "note": None}
            return {"reply": reply, "chart": render_line_multi(title, labels, series, metric),
                    "table": None, "title": title, "note": None}
        g = df.groupby("report_date")["_v"].sum().sort_index()
        labels = [d[5:] for d in g.index]
        values = g.tolist()
        if len(values) <= 1:  # 单点：汇总 + 各产线分解，避免单点折线
            by_line = df.groupby("production_line")["_v"].sum().sort_values(ascending=False)
            lbls = by_line.index.tolist()[:6]
            vls = by_line.tolist()[:6]
            title2 = f"{intent['range_desc']}各产线{mname}（MES）"
            reply2 = f"📊 {title2}：总{mname} **{fmt(sum(values), metric)}**，" + "、".join(
                f"{l} {fmt(v, metric)}" for l, v in zip(lbls, vls)) + "。"
            return {"reply": reply2, "chart": render_bar(title2, lbls, vls, metric),
                    "table": [{"label": l, "value": fmt(v, metric), "extra": ""} for l, v in zip(lbls, vls)],
                    "title": title2, "note": None}
        title = f"{intent['range_desc']}{mname}趋势（MES）"
        reply = (f"📈 {title}：总{mname} **{fmt(sum(values), metric)}**，"
                 f"最高 {fmt(max(values), metric)}（{labels[values.index(max(values))]}），"
                 f"最低 {fmt(min(values), metric)}（{labels[values.index(min(values))]}）。")
        return {"reply": reply, "chart": render_line(title, labels, values, metric),
                "table": None, "title": title, "note": None}

    # ---- 对比 / 排名 / 单值 ----
    asc = intent.get("direction") == "asc"
    if dim:
        group_col = {"line": "production_line", "product": "product_name"}[dim]
        g = df.groupby(group_col)["_v"].sum().sort_values(ascending=asc)
    else:
        g = df.groupby("production_line")["_v"].sum().sort_values(ascending=asc)
    labels = g.index.tolist()[:6]
    values = g.tolist()[:6]
    if qtype == "ranking":
        w = "最低" if asc else "最高"
        title = f"{intent['range_desc']}{mname}{w}的{dname or '产线'} TOP{len(labels)}（MES）"
        reply = f"🏆 {title}：" + "、".join(
            f"{i + 1}. {l} {fmt(v, metric)}" for i, (l, v) in enumerate(zip(labels, values))) + "。"
        return {"reply": reply, "chart": render_bar(title, labels, values, metric, horizontal=True),
                "table": [{"label": l, "value": fmt(v, metric), "extra": ""} for l, v in zip(labels, values)],
                "title": title, "note": None}
    title = f"{intent['range_desc']}各{dname or '产线'}{mname}对比（MES）"
    reply = f"📊 {title}：" + "、".join(f"{l} {fmt(v, metric)}" for l, v in zip(labels, values)) + "。"
    if labels:
        reply += f" 最高为 **{labels[0]}（{fmt(values[0], metric)}）**"
    return {"reply": reply, "chart": render_bar(title, labels, values, metric),
            "table": [{"label": l, "value": fmt(v, metric), "extra": ""} for l, v in zip(labels, values)],
            "title": title, "note": None}


async def _quality_rate(intent: dict, cfg_mes: dict) -> dict:
    metric = intent["metric"]
    mname = "良率" if metric == "yield" else "不良率"
    qtype = intent["type"]

    if qtype == "trend":
        days = (intent["date_to"] - intent["date_from"]).days + 1
        d = await api_get(cfg_mes, "/api/quality/trend", {"granularity": "day", "days": days})
        points = d.get("points") or []
        if not points:
            return _empty(intent["range_desc"])
        labels = [p.get("label", "") for p in points]
        key = "yield_rate" if metric == "yield" else "defect_rate"
        # MES 返回的是百分数值（97.91 = 97.91%），转成小数供 fmt 统一格式化
        values = [float(p.get(key, 0) or 0) / 100 for p in points]
        title = f"{intent['range_desc']}{mname}趋势（MES）"
        reply = (f"📈 {title}：当前 **{mname} {fmt(values[-1], metric)}**，"
                 f"区间最高 {fmt(max(values), metric)}（{labels[values.index(max(values))]}）。")
        return {"reply": reply, "chart": render_line(title, labels, values, metric),
                "table": None, "title": title, "note": None}

    if intent.get("dim"):
        # 工序维度：/api/quality/process-yield
        if intent["dim"] == "process":
            d = await api_get(cfg_mes, "/api/quality/process-yield")
            items = d.get("items") or []
            if not items:
                return _empty(intent["range_desc"])
            labels = [str(i.get("process", "")) for i in items]
            values = [float(i.get("yield_rate", 0) or 0) / 100 for i in items]
            if metric == "defect_rate":
                values = [1 - v for v in values]
            asc = intent.get("direction") == "asc"
            pairs = sorted(zip(labels, values), key=lambda x: x[1], reverse=not asc)[:8]
            labels, values = [p[0] for p in pairs], [p[1] for p in pairs]
            title = f"MES 各工序{mname}（{intent['range_desc']}）"
            reply = f"📊 {title}：" + "、".join(f"{l} {fmt(v, metric)}" for l, v in zip(labels, values)) + "。"
            return {"reply": reply, "chart": render_bar(title, labels, values, metric),
                    "table": [{"label": l, "value": fmt(v, metric), "extra": ""} for l, v in zip(labels, values)],
                    "title": title, "note": None}
        # 按产线/产品维度：用日产量报表的不良率近似
        from_, to_ = intent["date_from"].isoformat(), intent["date_to"].isoformat()
        rows = await fetch_daily_output(cfg_mes, date_from=from_, date_to=to_)
        if not rows:
            return _empty(intent["range_desc"])
        df = pd.DataFrame(rows)
        dim = intent["dim"]
        group_col = {"line": "production_line", "product": "product_name", "shift": "production_line"}.get(dim)
        if not group_col:
            raise MesError(f"MES 暂不支持按{intent['dim_name']}维度查询{mname}")
        g = df.groupby(group_col).apply(
            lambda x: (x["defect_qty"].sum() / x["actual_qty"].sum()) if x["actual_qty"].sum() else 0,
            include_groups=False)
        if metric == "yield":
            g = 1 - g
        asc = intent.get("direction") == "asc"
        g = g.sort_values(ascending=asc)
        labels, values = g.index.tolist()[:6], g.tolist()[:6]
        if qtype == "ranking":
            w = "最低" if asc else "最高"
            title = f"{intent['range_desc']}{mname}{w}的{intent['dim_name'] or '产线'} TOP{len(labels)}（MES）"
            reply = f"🏆 {title}：" + "、".join(
                f"{i + 1}. {l} {fmt(v, metric)}" for i, (l, v) in enumerate(zip(labels, values))) + "。"
            return {"reply": reply, "chart": render_bar(title, labels, values, metric, horizontal=True),
                    "table": [{"label": l, "value": fmt(v, metric), "extra": ""} for l, v in zip(labels, values)],
                    "title": title, "note": "按日产量报表不良数/产量近似计算"}
        title = f"{intent['range_desc']}各{intent['dim_name']}{mname}（MES）"
        reply = f"📊 {title}：" + "、".join(f"{l} {fmt(v, metric)}" for l, v in zip(labels, values)) + "。"
        return {"reply": reply, "chart": render_bar(title, labels, values, metric),
                "table": [{"label": l, "value": fmt(v, metric), "extra": ""} for l, v in zip(labels, values)],
                "title": title, "note": "按日产量报表不良数/产量近似计算"}

    d = await api_get(cfg_mes, "/api/quality/kpi", {"period": "day"})
    items = {i.get("key"): i for i in (d.get("items") or [])}
    pick = items.get("yield_rate" if metric == "yield" else "defect_rate")
    if not pick:
        raise MesError("MES 质量 KPI 返回缺少对应指标")
    title = f"MES 质量{mname}（{intent['range_desc']}）"
    reply = f"📊 MES 质量{mname}：**{pick.get('value')}{pick.get('unit', '%')}**"
    if pick.get("change_direction") and pick.get("change_direction") != "flat":
        reply += f"（较上期{pick.get('change_direction') == 'up' and '上升' or '下降'} {pick.get('change')}）"
    others = [i for k, i in items.items() if k != pick.get("key")]
    table = [{"label": i.get("label", ""), "value": f"{i.get('value')}{i.get('unit', '')}",
              "extra": i.get("change_direction", "")} for i in others]
    return {"reply": reply, "chart": None, "table": table, "title": title, "note": None}


async def _defect_share(intent: dict, cfg_mes: dict) -> dict:
    d = await api_get(cfg_mes, "/api/quality/defect-distribution", {"by": "type"})
    items = d.get("items") or []
    if not items:
        return _empty(intent["range_desc"])
    labels = [str(i.get("name", "")) for i in items]
    values = [float(i.get("value", 0) or 0) for i in items]
    total = sum(values) or 1
    title = f"MES 缺陷类型占比（{intent['range_desc']}）"
    pairs = sorted(zip(labels, values), key=lambda x: -x[1])
    reply = "🥧 " + title + "：" + "、".join(f"{l} {v / total * 100:.1f}%" for l, v in pairs[:8]) + "。"
    return {"reply": reply, "chart": render_pie(title, labels, values),
            "table": [{"label": l, "value": f"{v / total * 100:.1f}%", "extra": ""} for l, v in pairs],
            "title": title, "note": None}


async def _alarms(intent: dict, cfg_mes: dict) -> dict:
    d = await api_get(cfg_mes, "/api/device/alarms/trend")
    labels = d.get("labels") or []
    values = [float(v or 0) for v in (d.get("values") or [])]
    if not labels:
        return _empty(intent["range_desc"])
    title = "MES 设备告警趋势"
    reply = (f"🚨 {title}：累计 **{int(sum(values))}** 次，"
             f"最高 {int(max(values))} 次（{labels[values.index(max(values))]}）。")
    return {"reply": reply, "chart": render_line(title, labels, values, "downtime"),
            "table": [{"label": l, "value": f"{int(v)} 次", "extra": ""} for l, v in zip(labels, values)],
            "title": title, "note": "MES 提供的是告警次数（暂无停机时长）"}


async def _analyze_causes(intent: dict, cfg_mes: dict) -> dict:
    """原因分析：目标指标异常 → 当日值 vs 均值 + 按产线 + 缺陷构成 + 关联异常。"""
    target = intent["metric"]
    if target not in ("yield", "defect_rate"):
        raise MesError("暂只支持良率/不良率的原因分析")
    mname = "良率" if target == "yield" else "不良率"
    d1, d2 = intent["date_from"].isoformat(), intent["date_to"].isoformat()
    label = f"{d1} 至 {d2}" if d1 != d2 else d1

    # 1) 目标日 vs 近30天均值
    trend = await api_get(cfg_mes, "/api/quality/trend", {"granularity": "day", "days": 30})
    points = trend.get("points") or []
    key = "yield_rate" if target == "yield" else "defect_rate"

    def _v(p):
        try:
            return float(p.get(key, 0) or 0) / 100
        except Exception:
            return 0.0

    values = [_v(p) for p in points]
    target_val = None
    for p in points:
        if str(p.get("label", "")).replace("/", "-") in (d1[5:], d1.replace("-", "/")[5:]):
            target_val = _v(p)
            break
    if target_val is None and points:
        target_val = values[-1]
    mean_val = sum(values) / len(values) if values else 0
    head = f"📉 分析 {label} {mname}异常原因（MES）\n"
    if target_val is not None:
        diff = (target_val - mean_val) * 100
        head += (f"当日{mname} **{fmt(target_val, target)}**，近30天均值 {fmt(mean_val, target)}"
                 f"（{'低' if diff < 0 else '高'} {abs(diff):.1f}pct）\n")

    # 2) 按产线（日产量报表不良率）
    parts = []
    rows = await fetch_daily_output(cfg_mes, date_from=d1, date_to=d2)
    if rows:
        df = pd.DataFrame(rows)
        g = df.groupby("production_line").apply(
            lambda x: (x["defect_qty"].sum() / x["actual_qty"].sum()) if x["actual_qty"].sum() else 0,
            include_groups=False)
        if target == "yield":
            g = 1 - g
        g = g.sort_values(ascending=False)
        worst = g.index[0]
        detail = "、".join(f"{k} {fmt(v, target)}" for k, v in g.iloc[1:3].items())
        parts.append(f"① 按产线：**{worst}** 最差（{fmt(g.iloc[0], target)}）" +
                     (f"，其次 {detail}" if detail else ""))

    # 3) 缺陷构成
    dd = await api_get(cfg_mes, "/api/quality/defect-distribution", {"by": "type"})
    items = dd.get("items") or []
    total = sum(float(i.get("value", 0) or 0) for i in items) or 1
    top = sorted(items, key=lambda i: -float(i.get("value", 0) or 0))[:3]
    if top:
        parts.append("② 缺陷构成：" + "、".join(
            f"{i.get('name')} {float(i.get('value') or 0) / total * 100:.1f}%" for i in top))

    # 4) 关联异常
    anom = await api_get(cfg_mes, "/api/quality/anomalies", {"limit": 5})
    anom_items = anom.get("items") or []
    if anom_items:
        parts.append("③ 待处理异常：" + "、".join(
            f"{i.get('production_line')}-{i.get('defect_type')}({i.get('severity')})"
            for i in anom_items[:4]))

    reply = head + "\n".join(parts) + "\n\n建议优先排查上述产线与缺陷类型。"
    chart = None
    table = None
    if items:
        chart = render_pie(f"{label} 缺陷构成（全部时段）",
                           [str(i.get("name", "")) for i in items],
                           [float(i.get("value", 0) or 0) for i in items])
        table = [{"label": str(i.get("name", "")),
                  "value": f"{float(i.get('value') or 0) / total * 100:.1f}%", "extra": ""}
                 for i in items[:8]]
    return {"reply": reply, "chart": chart, "table": table,
            "title": f"{mname}过低原因分析（{label}）",
            "note": "基于 MES 质量趋势 / 日产量 / 缺陷分布 / 异常记录综合分析"}
