"""生產線模擬／分析（之後要換成正式的模擬，只改這個檔案）。

輸入：event 表的資料（欄位同 Excel：group_id, product_id, station_id, start_time,
      finish_time, duration_sec, wip_before_start, wip_after_finish, status）
輸出：(message, data)
      message 顯示在網頁上的一行文字（目標一）
      data    各組分析結果，存成 JSON（目標二）
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

TW = timezone(timedelta(hours=8))


def _dt(v) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def batch_of(product_id: str) -> str:
    """TEST1-P01 → TEST1；P01（正式）→ FORMAL"""
    p = str(product_id or "")
    return p.split("-")[0] if "-" in p else "FORMAL"


def analyze_line(rows: list[dict]) -> dict:
    """單一組別、單一批次的生產線指標。"""
    by_station: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get("duration_sec") is not None:
            by_station[r["station_id"]].append(float(r["duration_sec"]))
    stations = sorted(by_station)
    avg_ct = {s: round(statistics.fmean(v), 1) for s, v in by_station.items()}

    first, last = stations[0], stations[-1]
    started = {r["product_id"] for r in rows if r["station_id"] == first}
    finished = {r["product_id"] for r in rows if r["station_id"] == last}

    starts = [d for d in (_dt(r.get("start_time")) for r in rows) if d]
    ends = [d for d in (_dt(r.get("finish_time")) for r in rows) if d]
    elapsed = (max(ends) - min(starts)).total_seconds() if starts and ends else 0

    bottleneck = max(avg_ct, key=avg_ct.get)
    max_ct = avg_ct[bottleneck]
    balance = sum(avg_ct.values()) / (len(avg_ct) * max_ct) if max_ct else 0

    return {
        "events": len(rows),
        "stations": stations,
        "avg_ct": avg_ct,                                   # 各站平均作業秒數
        "count_by_station": {s: len(v) for s, v in by_station.items()},
        "bottleneck": bottleneck,                           # 瓶頸站（平均 CT 最大）
        "bottleneck_ct": max_ct,
        "balance_pct": round(balance * 100, 1),            # 產線平衡率
        "finished": len(finished),                          # 最後一站完成件數
        "wip": max(len(started) - len(finished), 0),        # 線上在製品
        "elapsed_min": round(elapsed / 60, 1),
        "throughput_per_hr": round(len(finished) / elapsed * 3600, 1) if elapsed else 0,
        "last_finish": max(ends).isoformat() if ends else None,
    }


def compute(tick: int, events: list[dict]) -> tuple[str, dict]:
    now = datetime.now(TW).strftime("%H:%M:%S")
    rows = [e for e in events if (e.get("status") or "COMPLETED") == "COMPLETED"]
    if not rows:
        return f"[{now}] Python 第 {tick} 次執行：event 表目前沒有資料", {"events": 0, "lines": []}

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["group_id"], batch_of(r["product_id"]))].append(r)

    lines = [
        {"group_id": g, "batch": b, **analyze_line(rs)}
        for (g, b), rs in sorted(grouped.items())
    ]
    all_stations = sorted({s for ln in lines for s in ln["stations"]})
    best = max(lines, key=lambda ln: (ln["throughput_per_hr"], ln["finished"]))

    data = {
        "events": len(rows),
        "groups": len({ln["group_id"] for ln in lines}),
        "stations": all_stations,
        "lines": lines,
        "best": {"group_id": best["group_id"], "batch": best["batch"], "throughput_per_hr": best["throughput_per_hr"]},
    }
    message = (
        f"[{now}] Python 第 {tick} 次執行：讀到 {len(rows)} 筆事件、{data['groups']} 組；"
        f"產出率最高為 {best['group_id']}（{best['batch']}）每小時 {best['throughput_per_hr']} 件，"
        f"其瓶頸站 {best['bottleneck']}（平均 {best['bottleneck_ct']} 秒）"
    )
    return message, data
