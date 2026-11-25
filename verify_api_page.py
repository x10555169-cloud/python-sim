"""驗證改良版 API 網頁（frontend/api.html）的計算核心跟 Python simulation.py 逐項相同。

只讀資料庫，不寫入。需要 Node.js。
用法（在 backend 資料夾）：python verify_api_page.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from simulation import compute
from verify_formulas import DATABASES

HERE = Path(__file__).resolve().parent
PAGE = HERE.parent / "frontend" / "api.html"
LINE_KEYS = ["events", "stations", "bottleneck", "bottleneck_ct", "balance_pct", "final_station", "output_station",
             "terminal_reached", "output_sets", "finished", "wip", "total_sec", "elapsed_min", "takt_sec",
             "steady_sec", "throughput_per_hr", "wait_sec", "long_span"]
STATION_KEYS = ["qty", "run_sec", "avg_ct", "wait_sec", "avg_wait", "util_pct", "pct_of_line", "vs_line_sec"]


def fetch(url: str, key: str, table: str) -> list[dict]:
    out, off = [], 0
    while True:
        rows = httpx.get(f"{url}/rest/v1/{table}", params={"select": "*", "limit": 1000, "offset": off, "order": "id.asc"},
                         headers={"apikey": key}, timeout=60).json()
        out += rows
        if len(rows) < 1000:
            return out
        off += 1000


def main() -> int:
    total_bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for db, (url, key) in DATABASES.items():
            ev, fl = fetch(url, key, "event"), fetch(url, key, "station_flow")
            evf, flf = Path(tmp, "ev.json"), Path(tmp, "fl.json")
            evf.write_text(json.dumps(ev)); flf.write_text(json.dumps(fl))
            _, d = compute(1, ev, fl)
            py = {(ln["group_id"], ln["batch"].replace("FORMAL", "PROD")): ln for ln in d["lines"]}
            out = subprocess.check_output(["node", str(HERE / "verify_api_page.js"), str(PAGE), str(evf), str(flf)])
            js = {(ln["group_id"], ln["round"]): ln for ln in json.loads(out)}
            n = bad = 0
            if set(py) != set(js):
                print(f"[{db}] 產線不一致：{sorted(set(py) ^ set(js))}")
                bad += 1
            for k in sorted(set(py) & set(js)):
                for f in LINE_KEYS:
                    n += 1
                    if py[k][f] != js[k][f]:
                        bad += 1
                        print(f"[{db}] {k} {f}：Python {py[k][f]!r}，網頁 {js[k][f]!r}")
                for st, v in py[k]["station_stats"].items():
                    for f in STATION_KEYS:
                        n += 1
                        if v[f] != js[k]["station_stats"][st][f]:
                            bad += 1
                            print(f"[{db}] {k} {st} {f}：Python {v[f]!r}，網頁 {js[k]['station_stats'][st][f]!r}")
            print(f"{db}：{len(ev)} 筆、{len(py)} 條產線、比對 {n} 項、不一致 {bad} 項")
            total_bad += bad
    print("全部一致 ✅" if not total_bad else f"有 {total_bad} 項不一致 ❌")
    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main())
