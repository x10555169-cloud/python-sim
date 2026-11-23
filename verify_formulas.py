"""公式驗證：用三種互相獨立的方法檢查 simulation.py 算出來的數字對不對。

  A. 人工驗算：自己設計的小資料，答案用手算（寫在註解裡），涵蓋各種特殊情況
  B. 獨立重算：用 pandas 從原始資料重新算一遍（完全不呼叫 simulation.py 的函式），逐項比對
  C. 老師算法：執行 verify_teacher.js（照抄老師監控中心的 JavaScript），逐項比對

用法（只讀資料庫，不寫入）：
    python verify_formulas.py              # 驗證甲班 + 測試資料庫
    python verify_formulas.py 甲班
    python verify_formulas.py 測試 --dump  # 另外存下原始資料（給 Excel 驗證表用）
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

from simulation import compute

HERE = Path(__file__).resolve().parent
DATABASES = {
    "甲班": ("https://iomsrjkrvuzrsluirtdj.supabase.co", "sb_publishable_QmLToEOs4wEEPBnASz0dxg_o0hhtgLO"),
    "測試": ("https://fqbsrcbxtmagczykoesv.supabase.co", "sb_publishable_mn0CAB_nkrDycq6DS3Q2_g_-80SlWHB"),
}

results: list[tuple[str, str, bool, str]] = []  # (部分, 項目, 通過?, 說明)
ROUND_TOL = 0.05 + 1e-6  # Python 顯示到小數 1 位；跟別的方法「未四捨五入」的值比，最多只能差 0.05


def check(part: str, name: str, got, want, tol: float = 0.0) -> bool:
    if (isinstance(want, float) or isinstance(got, float)) and not isinstance(want, bool):
        ok = (got is None and want is None) or (got is not None and want is not None and abs(float(got) - float(want)) <= tol + 1e-9)
    else:
        ok = got == want
    results.append((part, name, ok, f"得到 {got!r}，應為 {want!r}"))
    return ok


# ---------------------------------------------------------------- A. 人工驗算
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def ev(g, pid, st, start, dur, status="COMPLETED"):
    s = T0 + timedelta(seconds=start)
    return {"group_id": g, "product_id": pid, "station_id": st, "status": status, "duration_sec": dur,
            "start_time": s.isoformat(), "finish_time": (s + timedelta(seconds=dur)).isoformat()}


def flow(key, *edges):
    return [{"group_id": key, "station_id": a, "next_station_id": b} for a, b in edges]


def part_a() -> None:
    P = "A 人工驗算"
    events = [
        # A1 直線 ST01→ST02→ST03，兩件（秒數從 0 開始）
        ev("GA", "TEST1-P01", "ST01", 0, 10), ev("GA", "TEST1-P02", "ST01", 12, 8),
        ev("GA", "TEST1-P01", "ST02", 10, 20), ev("GA", "TEST1-P02", "ST02", 30, 22),
        ev("GA", "TEST1-P01", "ST03", 30, 5), ev("GA", "TEST1-P02", "ST03", 52, 7),
        # A2 組裝（ST01、ST02 → ST03），第 2 次測試沒有自己的流程 → 應沿用 GB-T1
        ev("GB", "TEST2-P01", "ST01", 0, 10), ev("GB", "TEST2-P01", "ST02", 0, 15), ev("GB", "TEST2-P01", "ST03", 15, 10),
        # A3 終點站 ST03 還沒完工
        ev("GC", "TEST1-P01", "ST01", 0, 10), ev("GC", "TEST1-P01", "ST02", 10, 20),
        # A4 資料清理：舊版 TEST-P01 → 第 1 次測試；P01 → 正式；未完工不算；超過 600 秒的空檔不算等待
        ev("GD", "TEST-P01", "ST01", 0, 10), ev("GD", "TEST1-P02", "ST01", 700, 10),
        ev("GD", "TEST1-P03", "ST01", 720, 10, status="IN_PROGRESS"), ev("GD", "P01", "ST01", 0, 5),
        # A5 跨天資料（第二件隔一天）
        ev("GE", "TEST1-P01", "ST01", 0, 10), ev("GE", "TEST1-P01", "ST02", 10, 10),
        ev("GE", "TEST1-P02", "ST01", 86400, 10), ev("GE", "TEST1-P02", "ST02", 86410, 10),
    ]
    flows = flow("GA-T1", ("ST01", "ST02"), ("ST02", "ST03"), ("ST03", None)) \
        + flow("GB-T1", ("ST01", "ST03"), ("ST02", "ST03")) \
        + flow("GC-T1", ("ST01", "ST02"), ("ST02", "ST03")) \
        + flow("GE-T1", ("ST01", "ST02"))
    modes = [{"group_id": "GA", "station_id": "GROUP_MODE", "input_wip": 103},
             {"group_id": "GB", "station_id": "GROUP_MODE", "input_wip": 1},
             {"group_id": "SYSTEM", "station_id": "SYSTEM_MODE", "input_wip": 101}]
    _, d = compute(1, events, flows, modes)
    L = {(l["group_id"], l["batch"]): l for l in d["lines"]}

    a1 = L[("GA", "TEST1")]
    # 總耗時 = 最晚完工 59 − 最早開工 0 = 59 秒；終點 ST03 產出 2 組 → 產線 CT 59 ÷ 2 = 29.5
    check(P, "A1 總耗時", a1["total_sec"], 59.0)
    check(P, "A1 終點站", a1["final_station"], "ST03")
    check(P, "A1 產出組數", a1["output_sets"], 2)
    check(P, "A1 產線 Cycle Time 59÷2", a1["takt_sec"], 29.5)
    check(P, "A1 每小時產出 3600÷29.5", a1["throughput_per_hr"], 122.0)
    # 平均 CT：ST01 (10+8)/2=9、ST02 (20+22)/2=21、ST03 (5+7)/2=6 → 瓶頸 ST02 21
    check(P, "A1 ST01 平均 CT", a1["avg_ct"]["ST01"], 9.0)
    check(P, "A1 ST02 平均 CT", a1["avg_ct"]["ST02"], 21.0)
    check(P, "A1 ST03 平均 CT", a1["avg_ct"]["ST03"], 6.0)
    check(P, "A1 瓶頸站", a1["bottleneck"], "ST02")
    # 平衡率 = (9+21+6) ÷ (3×21) = 36 ÷ 63 = 57.1%
    check(P, "A1 平衡率 36÷63", a1["balance_pct"], 57.1)
    # 等待：ST01 第2件 12−10=2；ST02 第1件 10−0=10、第2件 30−30=0；ST03 第1件 30−0=30、第2件 52−35=17
    check(P, "A1 ST01 等待 2", a1["station_stats"]["ST01"]["wait_sec"], 2.0)
    check(P, "A1 ST02 等待 10", a1["station_stats"]["ST02"]["wait_sec"], 10.0)
    check(P, "A1 ST03 等待 30+17", a1["station_stats"]["ST03"]["wait_sec"], 47.0)
    # 稼動率：ST01 18÷(18+2)=90.0%；ST02 42÷52=80.8%；ST03 12÷59=20.3%
    check(P, "A1 ST01 稼動率 18÷20", a1["station_stats"]["ST01"]["util_pct"], 90.0)
    check(P, "A1 ST02 稼動率 42÷52", a1["station_stats"]["ST02"]["util_pct"], 80.8)
    check(P, "A1 ST03 稼動率 12÷59", a1["station_stats"]["ST03"]["util_pct"], 20.3)
    check(P, "A1 等待合計 2+10+47", a1["wait_sec"], 59.0)
    # 穩態間隔：ST03 完工 35、59 → (59−35)÷1 = 24
    check(P, "A1 穩態間隔", a1["steady_sec"], 24.0)
    check(P, "A1 在製品 2−2", a1["wip"], 0)
    check(P, "A1 目前場次 GROUP_MODE=103 → 第 3 次測試，所以 TEST1 不是進行中", a1["is_current"], False)

    a2 = L[("GB", "TEST2")]
    check(P, "A2 沿用前一場流程 GB-T1", a2["flow_key"], "GB-T1")
    check(P, "A2 組裝線終點 ST03", a2["final_station"], "ST03")
    check(P, "A2 產線 CT 25÷1", a2["takt_sec"], 25.0)
    check(P, "A2 瓶頸 ST02 15", (a2["bottleneck"], a2["bottleneck_ct"]), ("ST02", 15.0))
    check(P, "A2 平衡率 35÷45", a2["balance_pct"], 77.8)
    check(P, "A2 ST03 等待 15−0", a2["station_stats"]["ST03"]["wait_sec"], 15.0)

    a3 = L[("GC", "TEST1")]
    check(P, "A3 終點站 ST03 未完工", a3["terminal_reached"], False)
    check(P, "A3 暫以 ST02 試算", (a3["output_station"], a3["output_sets"]), ("ST02", 1))
    check(P, "A3 產線 CT 30÷1（試算）", a3["takt_sec"], 30.0)
    check(P, "A3 未到終點 → 每小時產出 0、完成 0", (a3["throughput_per_hr"], a3["finished"]), (0, 0))
    check(P, "A3 在製品 1−0", a3["wip"], 1)

    check(P, "A4 TEST-P01 算第 1 次測試、未完工不算 → 2 筆", L[("GD", "TEST1")]["events"], 2)
    check(P, "A4 P01 算正式實作", ("GD", "FORMAL") in L, True)
    check(P, "A4 690 秒空檔 ≥ 600 不算等待", L[("GD", "TEST1")]["wait_sec"], 0.0)
    check(P, "A4 沒有流程 → 用有資料的最後一站", L[("GD", "TEST1")]["final_station"], "ST01")

    check(P, "A5 跨天資料標記", L[("GE", "TEST1")]["long_span"], True)
    check(P, "A6 最佳（排除未到終點、單站、跨天）", (d["best"]["group_id"], d["best"]["batch"]), ("GB", "TEST2"))
    check(P, "A6 GROUP_MODE=1 → 正式實作", d["current_rounds"].get("GB"), "FORMAL")
    check(P, "A6 SYSTEM_MODE=101 → 第 1 次測試（沒有 GROUP_MODE 的組別用這個）", d["system_round"], "TEST1")


# ---------------------------------------------------------------- 讀資料庫（唯讀）
def fetch(url: str, key: str, table: str, params: dict) -> list[dict]:
    rows, h = [], {"apikey": key}
    with httpx.Client(base_url=f"{url}/rest/v1", headers=h, timeout=30) as c:
        while True:
            r = c.get(f"/{table}", params={**params, "limit": 1000, "offset": len(rows)})
            if r.status_code == 404:
                return []
            r.raise_for_status()
            page = r.json()
            rows += page
            if len(page) < 1000:
                return rows


# ---------------------------------------------------------------- B. pandas 獨立重算
def independent(events: list[dict], flows: list[dict]) -> dict:
    """完全不使用 simulation.py，從原始資料重算每條線的指標。"""
    df = pd.DataFrame(events)
    df = df[df["status"].fillna("COMPLETED") == "COMPLETED"].copy()
    pid = df["product_id"].fillna("").str.strip().str.upper()
    num = pid.str.extract(r"^TEST(\d+)-")[0]
    df["round"] = "FORMAL"
    df.loc[pid.str.startswith("TEST"), "round"] = "TEST1"
    df.loc[num.notna(), "round"] = "TEST" + num[num.notna()].astype(int).astype(str)
    df["start"] = pd.to_datetime(df["start_time"], utc=True, format="ISO8601")
    df["finish"] = pd.to_datetime(df["finish_time"], utc=True, format="ISO8601")
    df["dur"] = pd.to_numeric(df["duration_sec"]).fillna(0.0)
    df["group_id"] = df["group_id"].str.strip()
    df["station_id"] = df["station_id"].str.strip()
    fdf = pd.DataFrame(flows) if flows else pd.DataFrame(columns=["group_id", "station_id", "next_station_id"])

    out = {}
    for (g, rnd), line in df.groupby(["group_id", "round"]):
        # 流程：本場 → 前面幾場 → 組別
        n = 10 if rnd == "FORMAL" else int(rnd[4:])
        keys = ([f"{g}-OFFICIAL"] if rnd == "FORMAL" else []) + [f"{g}-T{r}" for r in range(n, 0, -1)] + [g]
        edges = pd.DataFrame()
        for k in keys:
            e = fdf[fdf["group_id"].str.strip() == k]
            if len(e):
                edges = e
                break
        line_start = line["start"].min()
        per = {}
        for st, sdf in sorted(line.groupby("station_id"), key=lambda x: x[0]):
            sdf = sdf.sort_values("start", kind="stable")
            prev_end = sdf["finish"].shift(1)
            gaps = (sdf["start"] - prev_end.fillna(line_start)).dt.total_seconds()
            wait = gaps[(gaps > 0) & (gaps < 600)].sum()
            run = sdf["dur"].sum()
            # 一律保留「未四捨五入」的值，比對時允許 ±0.05（四捨五入最多造成的差距）
            per[st] = {"qty": len(sdf), "avg_ct": run / len(sdf), "wait_sec": wait,
                       "util_pct": run / (run + wait) * 100 if run + wait > 0 else 0}
        avg = {s: v["avg_ct"] for s, v in per.items()}
        mx = max(avg.values())
        bn = [s for s in sorted(avg) if avg[s] == mx][0]
        # 終點：沒有往外連線的工站，取編號最大
        final = None
        if len(edges):
            src = edges["station_id"].fillna("").str.strip()
            dst = edges["next_station_id"].fillna("").str.strip()
            nodes = set(src) | set(dst[dst != ""])
            has_out = set(src[dst != ""])
            terms = sorted(nodes - has_out)
            final = terms[-1] if terms else None
        stations = sorted(per)
        final = final or stations[-1]
        reached = final in per
        out_st = final if reached else stations[-1]
        out_n = per[out_st]["qty"]
        total = (line["finish"].max() - line_start).total_seconds()
        takt = total / out_n if out_n and total > 0 else None
        out[f"{g}|{rnd}"] = {
            "events": len(line), "final_station": final, "output_station": out_st, "terminal_reached": reached,
            "output_sets": out_n, "total_sec": total, "takt_sec": takt,
            "throughput_per_hr": 3600 / takt if takt and reached else 0,
            "bottleneck": bn, "bottleneck_ct": mx, "balance_pct": sum(avg.values()) / (len(avg) * mx) * 100,
            "wait_sec": sum(v["wait_sec"] for v in per.values()), "station_stats": per,
        }
    return out


FIELDS = ["events", "final_station", "output_station", "terminal_reached", "output_sets", "total_sec",
          "takt_sec", "throughput_per_hr", "bottleneck", "bottleneck_ct", "balance_pct", "wait_sec"]


def part_b_c(db: str, dump: bool) -> None:
    url, key = DATABASES[db]
    events = fetch(url, key, "event", {"select": "*", "order": "id.asc"})
    flows = fetch(url, key, "station_flow", {"select": "group_id,station_id,next_station_id"})
    modes = fetch(url, key, "station_wip", {"select": "group_id,station_id,input_wip", "station_id": "in.(GROUP_MODE,SYSTEM_MODE)"})
    print(f"\n[{db}] 讀到 event {len(events)} 筆、station_flow {len(flows)} 筆、目前場次 {len(modes)} 筆")
    _, d = compute(1, events, flows, modes)
    py = {f"{l['group_id']}|{l['batch']}": l for l in d["lines"]}

    # B
    P = f"B 獨立重算（{db}）"
    ind = independent(events, flows)
    check(P, "場次清單相同", sorted(ind), sorted(py))
    for k in sorted(set(ind) & set(py)):
        for f in FIELDS:
            want = ind[k][f]
            num = isinstance(want, float) and not isinstance(want, bool)
            check(P, f"{k} {f}", py[k][f], float(want) if num else want, ROUND_TOL if num else 0)
        for st, sv in ind[k]["station_stats"].items():
            for f in ("qty", "avg_ct", "wait_sec", "util_pct"):
                check(P, f"{k} {st} {f}", py[k]["station_stats"][st][f], sv[f] if f == "qty" else float(sv[f]), ROUND_TOL if f != "qty" else 0)

    # C
    P = f"C 老師算法（{db}）"
    node = shutil.which("node")
    tmp = HERE / ".verify_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "events.json").write_text(json.dumps(events), encoding="utf-8")
    (tmp / "flows.json").write_text(json.dumps(flows), encoding="utf-8")
    if not node:
        results.append((P, "略過：這台電腦沒有安裝 Node.js", True, ""))
    else:
        t = json.loads(subprocess.run([node, str(HERE / "verify_teacher.js"), str(tmp / "events.json"), str(tmp / "flows.json")],
                                      capture_output=True, text=True, check=True).stdout)
        check(P, "場次清單相同", sorted(t), sorted(py))
        for k in sorted(set(t) & set(py)):
            a, b = py[k], t[k]
            for f in ("events", "final_station", "output_station", "terminal_reached", "output_sets", "bottleneck"):
                check(P, f"{k} {f}", a[f], b[f])
            check(P, f"{k} total_sec", a["total_sec"], float(b["total_sec"]), ROUND_TOL)
            check(P, f"{k} takt_sec", a["takt_sec"], None if b["takt_sec"] is None else float(b["takt_sec"]), ROUND_TOL)
            check(P, f"{k} bottleneck_ct", a["bottleneck_ct"], float(b["bottleneck_ct"]), ROUND_TOL)
            for st, sv in b["station_stats"].items():
                for f in ("qty", "avg_ct", "wait_sec", "util_pct"):
                    want = sv[f] if f == "qty" else float(sv[f])
                    check(P, f"{k} {st} {f}", a["station_stats"][st][f], want, ROUND_TOL if f != "qty" else 0)
                # 佔產線 Cycle Time（整數 %，最多差 0.5）、差幾秒（小數 1 位，最多差 0.05）
                if sv["pct_of_line"] is not None:
                    check(P, f"{k} {st} 佔產線 Cycle Time %", a["station_stats"][st]["pct_of_line"], float(sv["pct_of_line"]), 0.5 + 1e-6)
                    check(P, f"{k} {st} 與產線 Cycle Time 差秒", a["station_stats"][st]["vs_line_sec"], float(sv["vs_line_sec"]), ROUND_TOL)
    if dump:
        out = HERE.parent / "verify" / db
        out.mkdir(parents=True, exist_ok=True)
        for name, obj in (("events", events), ("flows", flows), ("modes", modes), ("python_result", d)):
            (out / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    dbs = [a for a in sys.argv[1:] if a in DATABASES] or list(DATABASES)
    part_a()
    for db in dbs:
        part_b_c(db, "--dump" in sys.argv)

    print()
    parts: dict[str, list] = {}
    for p, n, ok, msg in results:
        parts.setdefault(p, []).append((n, ok, msg))
    total_fail = 0
    for p, items in parts.items():
        fails = [i for i in items if not i[1]]
        total_fail += len(fails)
        print(f"{'✔' if not fails else '✘'} {p}：{len(items) - len(fails)}/{len(items)} 項一致")
        for n, _, msg in fails:
            print(f"    ✘ {n}：{msg}")
    print(f"\n總計 {len(results)} 項檢查，{'全部通過' if not total_fail else f'{total_fail} 項不一致'}")
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
