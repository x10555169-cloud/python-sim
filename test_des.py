"""離散事件模擬（des.py）驗證：用「固定作業時間」的小例子，答案可以用手算（寫在註解裡）。

用法（在 backend 資料夾）：python test_des.py
"""
from __future__ import annotations

import sys

from des import build_model, simulate

results: list[tuple[str, bool, str]] = []


def check(name: str, got, want, tol: float = 1e-6) -> None:
    ok = abs(got - want) <= tol if isinstance(want, (int, float)) and not isinstance(want, bool) else got == want
    results.append((name, ok, f"得到 {got!r}，應為 {want!r}"))


def ev(st: str, i: int, dur: float, g: str = "G01", rnd: str = "TEST1") -> dict:
    s = f"2026-01-01T00:{i:02d}:00+00:00"
    return {"group_id": g, "product_id": f"{rnd}-P{i:02d}", "station_id": st, "status": "COMPLETED",
            "duration_sec": dur, "start_time": s, "finish_time": s}


def flow(key: str, *edges: tuple[str, str]) -> list[dict]:
    return [{"group_id": key, "station_id": a, "next_station_id": b} for a, b in edges]


def model(times: dict[str, float], edges, limits=None):
    events = [ev(st, i, d) for st, d in times.items() for i in range(3)]
    return build_model(events, flow("G01-T1", *edges), limits or [], "G01", "TEST1")


def run(m, n, **kw):
    return simulate(m, n_sets=n, reps=3, mode="mean", **kw)


# 1. 單站：每件 10 秒，做 5 組 → 50 秒；產線 Cycle Time 10 秒；利用率 100%
m = model({"ST01": 10}, [("ST01", "")])
r = run(m, 5)
check("1 單站 完成時間", r["makespan_sec"]["mean"], 50)
check("1 單站 Cycle Time", r["line_ct_sec"]["mean"], 10)
check("1 單站 利用率", r["stations"][0]["util_pct"], 100)

# 2. 串聯 ST01(10 秒) → ST02(20 秒)，不限 WIP，做 5 組：
#    ST02 從 10 秒開始一直忙：10 + 20×5 = 110 秒；穩態間隔 = 20 秒（瓶頸 ST02）
m = model({"ST01": 10, "ST02": 20}, [("ST01", "ST02")])
r = run(m, 5, wip="none")
check("2 串聯 完成時間", r["makespan_sec"]["mean"], 110)
check("2 串聯 穩態間隔", r["steady_sec"]["mean"], 20)
check("2 串聯 瓶頸", r["bottleneck"], "ST02")
check("2 串聯 ST02 利用率", r["stations"][1]["util_pct"], round(100 / 110 * 100, 1))   # 100 秒 ÷ 110 秒

# 3. 同上但 WIP 上限 1：ST01 第 3 件做完時 ST02 還在做第 1 件、緩衝區已有第 2 件 → ST01 被擋住（阻塞）
#    完成時間不變（還是被 ST02 卡住）= 110 秒；ST01 的阻塞時間 > 0
r = run(m, 5, wip=1)
check("3 WIP=1 完成時間", r["makespan_sec"]["mean"], 110)
check("3 WIP=1 ST01 有阻塞", r["stations"][0]["blocked_pct"] > 0, True)
check("3 WIP=1 緩衝區最多 1 件", r["buffers"][0]["max_wip"], 1)

# 4. 合流（組裝）：ST01(10 秒)、ST02(30 秒) → ST03(5 秒)，做 4 組：
#    ST03 要等 ST02 的料：第 k 組在 30k 秒到齊，做 5 秒 → 第 4 組 125 秒完成；瓶頸 ST02
m = model({"ST01": 10, "ST02": 30, "ST03": 5}, [("ST01", "ST03"), ("ST02", "ST03")])
r = run(m, 4, wip="none")
check("4 合流 完成時間", r["makespan_sec"]["mean"], 125)
check("4 合流 瓶頸", r["bottleneck"], "ST02")

# 5. 增加人數：同 4，但 ST02 兩個人 → ST02 每 30 秒出 2 件：第 1、2 組 30 秒到齊，第 3、4 組 60 秒
#    ST03 在 30、35 秒做完第 1、2 組；60 → 65、70 秒 → 完成時間 70 秒
r = run(m, 4, wip="none", servers={"ST02": 2})
check("5 ST02 兩人 完成時間", r["makespan_sec"]["mean"], 70)

# 6. 作業時間倍率：同 2，ST02 改成 50%（10 秒）→ 兩站都 10 秒：10 + 10×5 = 60 秒
m = model({"ST01": 10, "ST02": 20}, [("ST01", "ST02")])
r = run(m, 5, wip="none", factor={"ST02": 0.5})
check("6 倍率 50% 完成時間", r["makespan_sec"]["mean"], 60)

# 7. 阻塞會拖慢上游：ST01(10) → ST02(30) → ST03(10)，WIP=1，做 3 組（ST02 是瓶頸）：
#    ST03 在 ST02 做完後 10 秒完成：ST02 完成 40、70、100 → ST03 完成 110 秒
m = model({"ST01": 10, "ST02": 30, "ST03": 10}, [("ST01", "ST02"), ("ST02", "ST03")])
r = run(m, 3, wip=1)
check("7 三站 完成時間", r["makespan_sec"]["mean"], 110)

# 8. 資料庫的 WIP 上限：ST02_LIMIT = 3 會被讀進來
m = model({"ST01": 10, "ST02": 20}, [("ST01", "ST02")],
          limits=[{"group_id": "G01-T1", "station_id": "ST02_LIMIT", "input_wip": 3}])
check("8 讀到 ST02_LIMIT", m["wip_limits"]["ST02"], 3)
m = model({"ST01": 10, "ST02": 20}, [("ST01", "ST02")],
          limits=[{"group_id": "G01-T1", "station_id": "ST02_LIMIT", "input_wip": 0}])
check("8 LIMIT = 0 視為沒設定（用 2，同老師網頁）", m["wip_limits"]["ST02"], 2)

# 9. 隨機抽樣：同一個亂數種子結果相同（可重現）；抽樣的平均 CT 要接近實際平均
m = build_model([ev("ST01", i, d) for i, d in enumerate([5, 10, 15, 20])], flow("G01-T1", ("ST01", "")), [], "G01", "TEST1")
a = simulate(m, n_sets=200, reps=50, seed=7)
b = simulate(m, n_sets=200, reps=50, seed=7)
check("9 同種子結果相同", a["makespan_sec"], b["makespan_sec"])
check("9 抽樣平均接近 12.5 秒", abs(a["line_ct_sec"]["mean"] - 12.5) < 0.5, True)

fails = [x for x in results if not x[1]]
for name, ok, msg in results:
    print(("✅ " if ok else "❌ ") + name + ("" if ok else f"：{msg}"))
print(f"共 {len(results)} 項，失敗 {len(fails)} 項")
sys.exit(1 if fails else 0)
