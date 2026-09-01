"""演示数据生成（离线可用）。

在业务数据接入（P1）完成前，用合成数据跑通「聊天查数 → 分析 → 图表」全流程。
数据口径：
- 120 天、3 条产线（L1-L3）、6 个产品（A-01..C-01）、白/夜班
- work_orders：工单（计划/实际数量、达成率、产量）
- equipment_events：设备事件（运行/停机/维修/待机 → 可用率、停机、利用率）
- quality_records：质检（抽检/不良 → 良率、缺陷分布）
"""

import random
from datetime import date, timedelta

import pandas as pd

LINES = ["L1", "L2", "L3"]
PRODUCTS = ["A-01", "A-02", "A-03", "B-01", "B-02", "C-01"]
SHIFTS = ["白班", "夜班"]
DEFECT_TYPES = ["划伤", "尺寸超差", "外观不良", "功能异常", "其他"]
EVENT_TYPES = ["运行", "停机", "维修", "待机"]


def _w(rnd, lo, hi):
    return rnd.randint(lo, hi)


def generate(days: int = 120, seed: int = 42):
    rnd = random.Random(seed)
    today = date.today()
    wo_rows, ev_rows, qc_rows = [], [], []
    order_no = 1001

    for d in range(days - 1, -1, -1):
        day = today - timedelta(days=d)
        day_s = day.isoformat()
        for line in LINES:
            # ---- 设备事件（每日每线）----
            run_min = _w(rnd, 660, 900)
            down_min = _w(rnd, 20, 120) if rnd.random() < 0.85 else 0
            repair_min = _w(rnd, 30, 180) if rnd.random() < 0.5 else 0
            idle_min = _w(rnd, 30, 150) if rnd.random() < 0.7 else 0
            events = [("运行", run_min)]
            if down_min:
                events.append(("停机", down_min))
            if repair_min:
                events.append(("维修", repair_min))
            if idle_min:
                events.append(("待机", idle_min))
            eq = f"EQ-{line}-0{rnd.randint(1, 2)}"
            for i, (etype, dur) in enumerate(events):
                ev_rows.append({
                    "date": day_s, "line": line, "equipment": eq,
                    "event_type": etype, "duration_min": dur,
                    "start_time": f"{day_s} {8 + i * 4:02d}:00:00",
                })

            # ---- 工单 + 质检（每线每班次 1-3 单）----
            for shift in SHIFTS:
                for _ in range(_w(rnd, 1, 3)):
                    product = rnd.choice(PRODUCTS)
                    planned = _w(rnd, 200, 800)
                    actual = int(planned * rnd.uniform(0.82, 1.06))
                    status = "完成" if (d > 1 or rnd.random() < 0.9) else "进行中"
                    order = f"WO{day.strftime('%Y%m%d')}{order_no}"
                    wo_rows.append({
                        "work_order_no": order, "date": day_s, "line": line,
                        "shift": shift, "product": product,
                        "planned_qty": planned, "actual_qty": actual,
                        "status": status,
                    })
                    sample = _w(rnd, 20, 60)
                    defect = int(sample * rnd.uniform(0.005, 0.05))
                    qc_rows.append({
                        "work_order_no": order, "date": day_s, "line": line,
                        "product": product,
                        "inspect_time": f"{day_s} {8 + (0 if shift == '白班' else 12):02d}:30:00",
                        "sample_qty": sample, "defect_qty": defect,
                        "defect_type": rnd.choice(DEFECT_TYPES) if defect else "无",
                    })
                    order_no += 1

    return (
        pd.DataFrame(wo_rows),
        pd.DataFrame(ev_rows),
        pd.DataFrame(qc_rows),
    )


class DemoStore:
    """演示数据单例仓库。"""

    def __init__(self, days: int = 120, seed: int = 42):
        self.wo, self.ev, self.qc = generate(days=days, seed=seed)
        self.days = days
        self.range_desc = f"{self.wo['date'].min()} ~ {self.wo['date'].max()}"

    def summary(self) -> dict:
        return {
            "orders": int(len(self.wo)),
            "events": int(len(self.ev)),
            "quality": int(len(self.qc)),
            "lines": sorted(self.wo["line"].unique().tolist()),
            "products": sorted(self.wo["product"].unique().tolist()),
            "range": self.range_desc,
        }


_store = None


def get_demo_store() -> DemoStore:
    global _store
    if _store is None:
        _store = DemoStore()
    return _store
