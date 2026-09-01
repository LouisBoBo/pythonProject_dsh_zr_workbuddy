"""分析引擎：指标计算 + matplotlib 图表渲染（完全离线）。

指标口径：
- OEE = 可用率 × 性能率 × 良率
- 可用率 = 运行时长 / 总时长（设备事件）
- 性能率 = 实际产量 / (计划产量 × 0.92)（上限 1）
- 良率 = 1 - 不良数 / 抽检数
"""

import base64
import io
import os

import numpy as np
import pandas as pd

os.environ.setdefault(
    "MPLCONFIGDIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".mplcache"),
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

# ---------- 中文字体 ----------
_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
]
for _p in _FONT_CANDIDATES:
    if os.path.exists(_p):
        try:
            font_manager.fontManager.addfont(_p)
            _name = font_manager.FontProperties(fname=_p).get_name()
            plt.rcParams["font.sans-serif"] = [_name, "DejaVu Sans"]
            break
        except Exception:
            continue
plt.rcParams["axes.unicode_minus"] = False

PCT_METRICS = {"oee", "yield", "defect_rate", "achievement", "utilization", "defect_share"}
DIM_METRICS = {
    "line": {"oee", "yield", "defect_rate", "output", "planned", "achievement",
             "downtime", "utilization", "defect_share", "completed_orders",
             "in_progress_orders", "work_orders_total"},
    "product": {"yield", "defect_rate", "output", "planned", "achievement", "defect_share",
                "completed_orders", "in_progress_orders", "work_orders_total"},
    "shift": {"yield", "defect_rate", "output", "planned", "achievement", "completed_orders",
              "in_progress_orders", "work_orders_total"},
    "equipment": {"downtime", "utilization"},
}
_PALETTE = ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]


def fmt(v, metric):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    if metric in PCT_METRICS:
        return f"{v * 100:.1f}%"
    return f"{v:,.0f}"


# ---------- 事实表（按分组列计算指标） ----------

def _fact(wo: pd.DataFrame, qc: pd.DataFrame, ev: pd.DataFrame, g: list, metric: str) -> pd.DataFrame:
    """按 g 分组计算 metric，返回含分组列 + metric 值的 DataFrame。"""
    if metric in ("output", "planned", "achievement"):
        df = wo.groupby(g, as_index=False).agg(
            planned=("planned_qty", "sum"), actual=("actual_qty", "sum"))
        df["achievement"] = df["actual"] / df["planned"].replace(0, np.nan)
        df["output"] = df["actual"]
        return df

    if metric in ("yield", "defect_rate"):
        q = qc.groupby(g, as_index=False).agg(sample=("sample_qty", "sum"), defect=("defect_qty", "sum"))
        q["yield"] = 1 - q["defect"] / q["sample"].replace(0, np.nan)
        q["defect_rate"] = 1 - q["yield"]
        return q

    if metric == "defect_share":
        gg = g + ["defect_type"] if g else ["defect_type"]
        q = qc.groupby(gg, as_index=False)["defect_qty"].sum()
        tot = q["defect_qty"].sum() or 1
        q["defect_share"] = q["defect_qty"] / tot
        return q

    if metric == "downtime":
        return (ev[ev["event_type"] != "运行"]
                .groupby(g, as_index=False)["duration_min"].sum()
                .rename(columns={"duration_min": "downtime"}))

    if metric == "utilization":
        evd = ev.groupby(g + ["event_type"], as_index=False)["duration_min"].sum()
        piv = evd.pivot(index=g, columns="event_type", values="duration_min").fillna(0).reset_index()
        run = piv["运行"]
        tot = piv[[c for c in ("运行", "停机", "维修", "待机") if c in piv]].sum(axis=1)
        piv["utilization"] = run / tot.replace(0, np.nan)
        return piv[g + ["utilization"]]

    if metric == "oee":
        df = wo.groupby(g, as_index=False).agg(
            planned=("planned_qty", "sum"), actual=("actual_qty", "sum"))
        q = qc.groupby(g, as_index=False).agg(sample=("sample_qty", "sum"), defect=("defect_qty", "sum"))
        df = df.merge(q, on=g, how="left")
        y = 1 - df["defect"].fillna(0) / df["sample"].replace(0, np.nan)
        perf = (df["actual"] / (df["planned"] * 0.92)).clip(0, 1)
        if "line" in g:
            evd = ev.groupby(["date", "line", "event_type"], as_index=False)["duration_min"].sum()
            piv = evd.pivot(index=["date", "line"], columns="event_type", values="duration_min").fillna(0)
            run = piv["运行"]
            tot = piv[[c for c in ("运行", "停机", "维修", "待机") if c in piv]].sum(axis=1)
            avail_daily = (run / tot.replace(0, np.nan)).rename("avail").reset_index()
            if set(g) == {"date", "line"}:
                df = df.merge(avail_daily, on=g, how="left")
                avail = df["avail"].fillna(0.9)
            else:
                agg = avail_daily.groupby([c for c in g if c != "date"], as_index=False)["avail"].mean()
                df = df.merge(agg, on=[c for c in g if c != "date"], how="left")
                avail = df["avail"].fillna(0.9)
        else:
            avail = 0.9
        df["oee"] = avail * perf * y.fillna(0.95)
        return df

    if metric == "completed_orders":
        done = wo[wo["status"] == "完成"]
        return done.groupby(g).size().reset_index(name="completed_orders")

    if metric == "in_progress_orders":
        wip = wo[wo["status"] == "进行中"]
        return wip.groupby(g).size().reset_index(name="in_progress_orders")

    if metric == "work_orders_total":
        return wo.groupby(g).size().reset_index(name="work_orders_total")

    raise ValueError(f"不支持的指标: {metric}")


def _overall(wo: pd.DataFrame, qc: pd.DataFrame, ev: pd.DataFrame, metric: str):
    if metric == "output":
        return int(wo["actual_qty"].sum())
    if metric == "planned":
        return int(wo["planned_qty"].sum())
    if metric == "achievement":
        return wo["actual_qty"].sum() / wo["planned_qty"].sum()
    if metric in ("yield", "defect_rate"):
        y = 1 - qc["defect_qty"].sum() / qc["sample_qty"].sum()
        return y if metric == "yield" else 1 - y
    if metric == "downtime":
        return int(ev[ev["event_type"] != "运行"]["duration_min"].sum())
    if metric == "utilization":
        run = ev[ev["event_type"] == "运行"]["duration_min"].sum()
        return run / ev["duration_min"].sum()
    if metric == "oee":
        a = ev[ev["event_type"] == "运行"]["duration_min"].sum() / ev["duration_min"].sum()
        p = min(wo["actual_qty"].sum() / (wo["planned_qty"].sum() * 0.92), 1)
        y = 1 - qc["defect_qty"].sum() / qc["sample_qty"].sum()
        return a * p * y
    if metric == "defect_share":
        return qc["defect_qty"].sum()
    if metric == "completed_orders":
        return int((wo["status"] == "完成").sum())
    if metric == "in_progress_orders":
        return int((wo["status"] == "进行中").sum())
    if metric == "work_orders_total":
        return int(len(wo))
    return None


# ---------- 图表渲染 ----------

def _fig(w=8.6, h=4.0):
    fig, ax = plt.subplots(figsize=(w, h), dpi=110)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fafbfc")
    ax.grid(True, alpha=0.3, linestyle="--")
    return fig, ax


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _pct_axis(ax, metric):
    """百分比指标：Y 轴刻度显示为百分数（0.975 → 97.5%）。"""
    if metric in PCT_METRICS:
        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))


def render_line(title, labels, values, metric):
    fig, ax = _fig()
    ax.plot(labels, values, marker="o", markersize=3.2, linewidth=1.8, color=_PALETTE[0])
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_ylabel("", fontsize=9)
    if len(labels) > 8:
        ax.tick_params(axis="x", rotation=45, labelsize=8)
    else:
        ax.tick_params(labelsize=9)
    _pct_axis(ax, metric)
    return _png(fig)


def render_line_multi(title, labels, series, metric=None):
    fig, ax = _fig()
    for i, s in enumerate(series):
        ax.plot(labels, s["data"], marker="o", markersize=2.5, linewidth=1.6,
                color=_PALETTE[i % len(_PALETTE)], label=s["name"])
    ax.set_title(title, fontsize=12, pad=10)
    ax.legend(fontsize=8, frameon=False, ncol=len(series) if len(series) > 1 else 1)
    if len(labels) > 8:
        ax.tick_params(axis="x", rotation=45, labelsize=8)
    else:
        ax.tick_params(labelsize=9)
    _pct_axis(ax, metric)
    return _png(fig)


def render_bar(title, labels, values, metric, horizontal=False):
    fig, ax = _fig()
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(labels))]
    if horizontal:
        order = slice(None, None, -1)
        ax.barh([str(l) for l in labels][order], values[order], color=colors[order])
        for i, (l, v) in enumerate(zip(labels[order], values[order])):
            ax.text(v, i, " " + fmt(v, metric), va="center", fontsize=9, color="#374151")
    else:
        ax.bar([str(l) for l in labels], values, color=colors, width=0.55)
        for i, v in enumerate(values):
            ax.text(i, v, fmt(v, metric), ha="center", va="bottom", fontsize=9, color="#374151")
    ax.set_title(title, fontsize=12, pad=10)
    ax.tick_params(labelsize=9)
    _pct_axis(ax, metric)
    return _png(fig)


def render_pie(title, labels, values):
    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=110)
    fig.patch.set_facecolor("white")
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(labels))]
    ax.pie(values, labels=[str(l) for l in labels], autopct="%1.1f%%",
           startangle=90, counterclock=False, colors=colors,
           textprops={"fontsize": 9}, wedgeprops={"edgecolor": "white", "linewidth": 1.2})
    ax.set_title(title, fontsize=12, pad=10)
    ax.axis("equal")
    return _png(fig)


# ---------- 主分析入口 ----------

def analyze(store, intent: dict) -> dict:
    wo = store.wo.copy()
    qc = store.qc.copy()
    ev = store.ev.copy()
    # 质检补充班次（由工单关联）
    qc = qc.merge(wo[["work_order_no", "shift"]].drop_duplicates(), on="work_order_no", how="left")

    from_, to_ = intent["date_from"].isoformat(), intent["date_to"].isoformat()
    wo = wo[(wo["date"] >= from_) & (wo["date"] <= to_)]
    qc = qc[(qc["date"] >= from_) & (qc["date"] <= to_)]
    ev = ev[(ev["date"] >= from_) & (ev["date"] <= to_)]
    for k, v in intent["filters"].items():
        if k in wo.columns:
            wo = wo[wo[k] == v]
        if k in qc.columns:
            qc = qc[qc[k] == v]
        if k in ev.columns:
            ev = ev[ev[k] == v]
    if wo.empty:
        return {"reply": "该时间范围内没有数据，换个时间试试。", "chart": None, "table": None, "note": None}

    metric = intent["metric"]
    dim = intent["dim"]
    qtype = intent["type"]
    mname = intent.get("metric_name") or metric
    dname = intent.get("dim_name") or ""
    note = None

    # 维度-指标白名单
    if dim and metric not in DIM_METRICS.get(dim, set()):
        note = f"（{dname}维度暂不支持{mname}，已展示整体数据）"
        dim = None

    filtered_dim = bool(dim and dim in intent["filters"])

    # ---------- 原因分析（演示兜底） ----------
    if qtype == "analysis":
        if metric not in ("yield", "defect_rate"):
            metric = "yield"
            mname = "良率"
        overall = _overall(wo, qc, ev, metric)
        by_line = _fact(wo, qc, ev, ["line"], metric).sort_values(metric, ascending=False)
        share = qc.groupby("defect_type")["defect_qty"].sum().sort_values(ascending=False)
        total_share = share.sum() or 1
        title = f"{intent['range_desc']}{mname}异常原因分析（演示）"
        head = f"📉 分析 {intent['range_desc']} {mname}异常原因（演示数据）\n整体{mname} **{fmt(overall, metric)}**\n"
        line_txt = "① 按产线：" + "、".join(f"{r['line']} {fmt(r[metric], metric)}" for _, r in by_line.head(3).iterrows()) if len(by_line) else ""
        def_txt = "② 缺陷构成：" + "、".join(f"{k} {v / total_share * 100:.1f}%" for k, v in share.head(3).items()) if len(share) else ""
        reply = head + line_txt + ("\n" if line_txt else "") + def_txt + "\n\n建议优先排查上述产线与缺陷类型。"
        return {"reply": reply,
                "chart": render_pie(f"{intent['range_desc']} 缺陷构成（演示）",
                                    share.index.tolist(), share.tolist()) if len(share) else None,
                "table": [{"label": k, "value": f"{v / total_share * 100:.1f}%", "extra": ""}
                          for k, v in share.head(8).items()] if len(share) else None,
                "title": title, "note": "演示数据归因分析"}

    # ---------- 占比 ----------
    if qtype == "share":
        g = [dim] if (dim and not filtered_dim) else []
        df = _fact(wo, qc, ev, g, "defect_share")
        label_col = "defect_type" if not g else g[0]
        pairs = sorted(zip(df[label_col].tolist(), (df["defect_share"] * 100).tolist()), key=lambda x: -x[1])
        labels = [p[0] for p in pairs]
        values = [p[1] for p in pairs]
        title = f"{intent['range_desc']}{'各' + dname if g else ''}缺陷占比"
        reply = f"🥧 {title}："
        reply += "、".join(f"{l} {v:.1f}%" for l, v in pairs[:8]) + ("…" if len(pairs) > 8 else "") + "。"
        return {
            "reply": reply, "chart": render_pie(title, labels, values),
            "table": [{"label": l, "value": f"{v:.1f}%", "extra": ""} for l, v in pairs],
            "note": note, "title": title,
        }

    # ---------- 趋势 ----------
    if qtype == "trend":
        days = (intent["date_to"] - intent["date_from"]).days
        if days <= 2 and not (dim and not filtered_dim):
            # 短区间 → 单值 + 产线分解
            overall = _overall(wo, qc, ev, metric)
            by_line = _fact(wo, qc, ev, ["line"], metric).sort_values(metric, ascending=False)
            parts = "、".join(f"{r['line']} {fmt(r[metric], metric)}" for _, r in by_line.iterrows())
            reply = f"📊 {intent['range_desc']}总{mname}：**{fmt(overall, metric)}**（{parts}）。"
            title = f"{intent['range_desc']}各产线{mname}"
            return {
                "reply": reply,
                "chart": render_bar(title, by_line["line"].tolist(), by_line[metric].tolist(), metric),
                "table": [{"label": r["line"], "value": fmt(r[metric], metric), "extra": ""}
                          for _, r in by_line.iterrows()],
                "note": note, "title": title,
            }

        if dim and not filtered_dim:
            g = ["date", dim]
            df = _fact(wo, qc, ev, g, metric)
            pivot = df.pivot(index="date", columns=dim, values=metric).sort_index()
            labels = [d[5:] for d in pivot.index]
            series = [{"name": c, "data": pivot[c].tolist()} for c in pivot.columns]
            title = f"{intent['range_desc']}各{dname}{mname}趋势"
            latest = pivot.iloc[-1]
            best, worst = pivot.mean(axis=1).idxmax(), pivot.mean(axis=1).idxmin()
            reply = (f"📈 {intent['range_desc']}各{dname}{mname}趋势："
                     f"平均最高出现在 {best[5:]}（{fmt(pivot.mean(axis=1).max(), metric)}），"
                     f"最低在 {worst[5:]}（{fmt(pivot.mean(axis=1).min(), metric)}）。")
            return {
                "reply": reply, "chart": render_line_multi(title, labels, series, metric),
                "table": None, "note": note, "title": title,
            }

        df = _fact(wo, qc, ev, ["date"], metric).sort_values("date")
        labels = [d[5:] for d in df["date"]]
        values = df[metric].tolist()
        mean_v = float(np.nanmean(values)) if values else 0
        mx, mn = max(values), min(values)
        mx_d, mn_d = labels[values.index(mx)], labels[values.index(mn)]
        first, last = values[0], values[-1]
        chg = f"较区间首日{'上升' if last >= first else '下降'} {abs(last - first) / first * 100:.1f}%" if first else ""
        title = f"{intent['range_desc']}{mname}趋势"
        reply = (f"📈 {title}：均值 **{fmt(mean_v, metric)}**，"
                 f"最高 {fmt(mx, metric)}（{mx_d}），最低 {fmt(mn, metric)}（{mn_d}）。{chg}")
        return {
            "reply": reply, "chart": render_line(title, labels, values, metric),
            "table": None, "note": note, "title": title,
        }

    # ---------- 对比 / 排名 ----------
    g = [dim or "line"]
    df = _fact(wo, qc, ev, g, metric).dropna(subset=[metric])
    if df.empty:
        return {"reply": "该维度没有可计算的数据。", "chart": None, "table": None, "note": note}
    asc = intent.get("direction") == "asc"
    df = df.sort_values(metric, ascending=asc)
    df = df.head(6)
    labels = df[g[0]].tolist()
    values = df[metric].tolist()

    if qtype == "ranking":
        direction_word = "最低" if asc else "最高"
        title = f"{intent['range_desc']}{mname}{direction_word}的{dname or '产线'} TOP{len(labels)}"
        reply = f"🏆 {title}：" + "、".join(
            f"{i + 1}. {l} {fmt(v, metric)}" for i, (l, v) in enumerate(zip(labels, values))) + "。"
        return {
            "reply": reply, "chart": render_bar(title, labels, values, metric, horizontal=True),
            "table": [{"label": l, "value": fmt(v, metric), "extra": ""} for l, v in zip(labels, values)],
            "note": note, "title": title,
        }

    title = f"{intent['range_desc']}各{dname or '产线'}{mname}对比"
    reply = f"📊 {title}：" + "、".join(
        f"{l} {fmt(v, metric)}" for l, v in zip(labels, values)) + "。"
    reply += f" 最高为 **{labels[0]}（{fmt(values[0], metric)}）**" if not asc else \
        f" 最低为 **{labels[0]}（{fmt(values[0], metric)}）**"
    return {
        "reply": reply, "chart": render_bar(title, labels, values, metric),
        "table": [{"label": l, "value": fmt(v, metric), "extra": ""} for l, v in zip(labels, values)],
        "note": note, "title": title,
    }
