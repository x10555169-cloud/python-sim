"""離散事件模擬（Discrete-Event Simulation, DES）：用學生收集到的資料，模擬產線「如果……會怎樣」。

跟 simulation.py 的差別：
  simulation.py  統計分析：把「已經發生」的紀錄整理成 CT、瓶頸、產線 Cycle Time
  des.py         模擬：用這些紀錄建立模型，讓電腦「假裝生產」很多次，預測結果、比較不同方案

模型（每一組 + 每一個場次各自一個模型）：
  工站與流程   station_flow（同老師的候選順序 T3 → T2 → T1 → 組別）；沒有流程時：
               有 ST09 → 老師網頁預設的 9 站組裝流程；否則依工站編號串聯
  作業時間     從該場次實際的 duration_sec 隨機抽一筆（bootstrap 抽樣），再乘上「作業時間倍率」
               也可以選「固定平均值」（每件都用平均 CT，沒有波動）
  合流（組裝） 有好幾個前站的工站，要每個前站各送來 1 件才能開工（齊套）
  起點站       原料無限，最多投入 N 件（N = 要生產的組數）
  站間緩衝區   上限 = station_wip 的「下一站_LIMIT」，沒設定用 2（同老師網頁）；可改成不限制
  阻塞         做完時下一站的緩衝區滿了 → 拿著成品等（佔住人手），直到有空位
  人數         每站幾個人（同時能做幾件），預設 1
  結束         終點站完成 N 組

一次模擬 = 一次假想的生產；重複 R 次（每次的亂數不同），取平均與 90% 範圍（第 5～95 百分位）。
只用 Python 內建模組，可以在瀏覽器（Pyodide）裡執行。
"""
from __future__ import annotations

import heapq
import random
from collections import defaultdict, deque

from simulation import analyze_line, edges_of, flow_for, round_label, round_of, terminal_station

DEFAULT_WIP_LIMIT = 2
DEFAULT_FLOW_9 = [("ST01", "ST05"), ("ST02", "ST05"), ("ST03", "ST06"), ("ST04", "ST06"),
                  ("ST05", "ST07"), ("ST06", "ST07"), ("ST07", "ST08"), ("ST08", "ST09")]


# ---------------------------------------------------------------- 1. 建立模型
def build_model(events: list[dict], flows: list[dict], limits: list[dict], group: str, rnd: str) -> dict:
    """從資料庫的資料建立某組某場次的模型（工站、流程、作業時間、緩衝區上限、實際結果）。"""
    rows = [e for e in events if (e.get("status") or "COMPLETED") == "COMPLETED"
            and (e.get("group_id") or "").strip() == group and round_of(e.get("product_id")) == rnd]
    if not rows:
        return {"ok": False, "error": f"{group} {round_label(rnd)} 沒有完工紀錄，無法建立模型"}

    flows_by_key: dict[str, list[dict]] = defaultdict(list)
    for f in flows or []:
        flows_by_key[(f.get("group_id") or "").strip()].append(f)
    key, flow = flow_for(flows_by_key, group, rnd)
    real_edges = edges_of(flow)
    times: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        d = float(r.get("duration_sec") or 0)
        if d > 0:
            times[(r.get("station_id") or "").strip()].append(d)
    with_data = sorted(times)

    if real_edges:
        edges = [(a, b) for a, b in real_edges if b]
        source = f"老師設定的流程（station_flow：{key}）"
    elif "ST09" in with_data:
        edges = list(DEFAULT_FLOW_9)
        source = "沒有設定流程 → 用老師網頁預設的 9 站組裝流程"
    else:
        edges = list(zip(with_data, with_data[1:]))
        source = "沒有設定流程 → 依工站編號串聯"
    nodes = sorted({a for a, _ in edges} | {b for _, b in edges} | (set() if edges else set(with_data)))
    preds = {s: sorted(a for a, b in edges if b == s) for s in nodes}
    succs = {s: sorted(b for a, b in edges if a == s) for s in nodes}
    terminal = terminal_station([(a, b) for a, b in edges] + [(s, "") for s in nodes if not succs[s]])

    # 沒有任何紀錄的工站（例如流程有、但還沒做到）：暫用全線作業時間中位數，並標示
    all_times = sorted(t for ts in times.values() for t in ts)
    median = all_times[len(all_times) // 2] if all_times else 1.0
    missing = [s for s in nodes if not times.get(s)]

    # 緩衝區上限：station_wip 的「ST05_LIMIT」= 送進 ST05 的緩衝區上限（同老師網頁 ApiFlow）
    lim: dict[str, int] = {}
    for want in (f"{group}-OFFICIAL" if rnd == "FORMAL" else f"{group}-T{rnd[4:]}", group):
        for r in limits or []:
            sid = (r.get("station_id") or "").strip()
            if (r.get("group_id") or "").strip() == want and sid.endswith("_LIMIT"):
                try:
                    v = int(float(r.get("input_wip")))
                except (TypeError, ValueError):
                    v = 0
                lim.setdefault(sid[:-6], v if v > 0 else DEFAULT_WIP_LIMIT)   # 0 或空白 = 沒設定（同老師網頁 Number(x) || 2）
        if lim:
            break

    actual = analyze_line(rows, real_edges)
    stations = []
    for s in nodes:
        ts = times.get(s) or []
        stations.append({
            "station": s, "preds": preds[s], "succs": succs[s],
            "count": len(ts), "mean": round(sum(ts) / len(ts), 1) if ts else None,
            "min": min(ts) if ts else None, "max": max(ts) if ts else None,
            "no_data": s in missing, "wip_limit_in": lim.get(s, DEFAULT_WIP_LIMIT) if preds[s] else None,
        })
    ignored = [s for s in with_data if s not in nodes]
    return {
        "ok": True, "group_id": group, "round": rnd, "round_label": round_label(rnd),
        "flow_source": source, "edges": [list(e) for e in edges], "terminal": terminal,
        "roots": [s for s in nodes if not preds[s]], "stations": stations,
        "times": {s: (times.get(s) or [median]) for s in nodes},
        "wip_limits": {s: lim.get(s, DEFAULT_WIP_LIMIT) for s in nodes if preds[s]},
        "wip_limit_source": "station_wip 的 _LIMIT 設定" if lim else f"沒有設定 → 預設 {DEFAULT_WIP_LIMIT}",
        "missing_data": missing, "ignored_stations": ignored,
        "actual": {k: actual[k] for k in ("output_sets", "total_sec", "takt_sec", "steady_sec", "bottleneck",
                                          "bottleneck_ct", "terminal_reached", "output_station", "events")},
    }


# ---------------------------------------------------------------- 2. 模擬引擎（一次假想的生產）
class LineSim:
    """事件驅動：時間直接跳到下一個「某站做完」的時刻，在那一刻更新所有狀態。"""

    def __init__(self, model: dict, n_sets: int, rng: random.Random, factor: dict, servers: dict,
                 cap: dict, mode: str):
        self.m, self.n, self.rng, self.mode = model, n_sets, rng, mode
        self.nodes = [s["station"] for s in model["stations"]]
        self.preds = {s["station"]: s["preds"] for s in model["stations"]}
        self.succs = {s["station"]: s["succs"] for s in model["stations"]}
        self.term = model["terminal"]
        self.times = model["times"]
        self.mean = {s: sum(v) / len(v) for s, v in self.times.items()}
        self.factor = {s: factor.get(s, 1.0) for s in self.nodes}
        self.k = {s: max(1, int(servers.get(s, 1))) for s in self.nodes}
        self.cap = cap                                     # cap[下一站] = 上限；None = 不限制
        self.buf = {(a, b): 0 for a, b in model["edges"]}   # 站間緩衝區目前件數
        self.busy = defaultdict(int)                        # 正在加工的件數
        self.blocked: dict[str, deque] = defaultdict(deque)  # 做完但送不出去的件（記下開始等的時間）
        self.released = defaultdict(int)                    # 起點站已投入件數
        self.proc_time = defaultdict(float)                 # 各站加工時間合計
        self.block_time = defaultdict(float)                # 各站阻塞時間合計
        self.done_times: list[float] = []
        self.heap: list[tuple[float, int, str]] = []
        self.seq = 0
        self.t = 0.0
        self.buf_area = defaultdict(float)
        self.buf_max = defaultdict(int)
        self.last_t = 0.0

    def sample(self, s: str) -> float:
        base = self.mean[s] if self.mode == "mean" else self.rng.choice(self.times[s])
        return max(0.001, base * self.factor[s])

    def _acc(self) -> None:                                 # 緩衝區件數 × 經過時間（算時間加權平均 WIP）
        dt = self.t - self.last_t
        if dt > 0:
            for e, q in self.buf.items():
                self.buf_area[e] += q * dt
            self.last_t = self.t

    def _has_space(self, s: str) -> bool:
        return all(self.cap.get(v) is None or self.buf[(s, v)] < self.cap[v] for v in self.succs[s])

    def _push(self, s: str) -> None:                        # 做好的件放進每個下一站的緩衝區
        self._acc()
        for v in self.succs[s]:
            self.buf[(s, v)] += 1
            self.buf_max[(s, v)] = max(self.buf_max[(s, v)], self.buf[(s, v)])
        for v in self.succs[s]:
            self.try_start(v)

    def try_start(self, s: str) -> None:
        while self.busy[s] + len(self.blocked[s]) < self.k[s]:      # 還有空的人手
            if not self.preds[s]:                                  # 起點站：原料無限，最多投入 N 件
                if self.released[s] >= self.n:
                    return
                self.released[s] += 1
            else:                                                  # 齊套：每個前站都要有 1 件
                if any(self.buf[(p, s)] < 1 for p in self.preds[s]):
                    return
                self._acc()
                for p in self.preds[s]:
                    self.buf[(p, s)] -= 1
            d = self.sample(s)
            self.proc_time[s] += d
            self.busy[s] += 1
            self.seq += 1
            heapq.heappush(self.heap, (self.t + d, self.seq, s))
            for p in self.preds[s]:                                # 緩衝區空出位置 → 上游被擋住的件可以送出
                self.try_unblock(p)

    def try_unblock(self, s: str) -> None:
        while self.blocked[s] and self._has_space(s):
            self.block_time[s] += self.t - self.blocked[s].popleft()
            self._push(s)
        self.try_start(s)

    def finish(self, s: str) -> None:
        self.busy[s] -= 1
        if s == self.term:
            self.done_times.append(self.t)
        elif self.succs[s]:
            if self._has_space(s):
                self._push(s)
            else:
                self.blocked[s].append(self.t)                     # 下一站滿了：拿著等
        self.try_start(s)

    def run(self) -> dict:
        for s in self.nodes:
            self.try_start(s)
        while self.heap and len(self.done_times) < self.n:
            t, _, s = heapq.heappop(self.heap)
            self.t = t
            self.finish(s)
        end = self.t
        self._acc()
        for tf, _, s in self.heap:                                 # 結束時還在加工的件：超過結束時間的部分不算
            self.proc_time[s] -= max(0.0, tf - end)
        for s, q in self.blocked.items():
            for t0 in q:
                self.block_time[s] += end - t0
        stats = {}
        for s in self.nodes:
            cap_time = self.k[s] * end if end > 0 else 1.0
            util = self.proc_time[s] / cap_time
            blk = self.block_time[s] / cap_time
            stats[s] = {"util": util, "blocked": blk, "starved": max(0.0, 1 - util - blk)}
        return {
            "finished": len(self.done_times), "makespan": end,
            "first_out": self.done_times[0] if self.done_times else None,
            "stations": stats,
            "buffers": {f"{a}→{b}": {"avg": (self.buf_area[(a, b)] / end) if end > 0 else 0,
                                     "max": self.buf_max[(a, b)]} for a, b in self.buf},
        }


# ---------------------------------------------------------------- 3. 重複模擬、統計
def _q(vals: list[float], p: float) -> float:
    v = sorted(vals)
    if not v:
        return 0.0
    i = (len(v) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def _summ(vals: list[float], nd: int = 1) -> dict:
    return {"mean": round(sum(vals) / len(vals), nd), "p5": round(_q(vals, 0.05), nd),
            "p95": round(_q(vals, 0.95), nd), "min": round(min(vals), nd), "max": round(max(vals), nd)}


def simulate(model: dict, n_sets: int = 10, reps: int = 200, seed: int = 2026, mode: str = "sample",
             factor: dict | None = None, servers: dict | None = None, wip: str | int = "db") -> dict:
    """跑 reps 次模擬。wip："db" = 資料庫設定（沒有用 2）；整數 = 全部緩衝區同一個上限；"none" = 不限制。"""
    if not model.get("ok"):
        return model
    n_sets, reps = max(1, int(n_sets)), max(1, min(int(reps), 2000))
    factor = {k: float(v) for k, v in (factor or {}).items()}
    servers = {k: int(v) for k, v in (servers or {}).items()}
    if wip == "none":
        cap = {s: None for s in model["wip_limits"]}
    elif wip == "db":
        cap = dict(model["wip_limits"])
    else:
        cap = {s: max(1, int(wip)) for s in model["wip_limits"]}

    runs = [LineSim(model, n_sets, random.Random(seed + i), factor, servers, cap, mode).run() for i in range(reps)]
    ok = [r for r in runs if r["finished"] >= n_sets]
    if not ok:
        return {"ok": False, "error": "模擬無法完成（流程可能有斷點），請檢查流程設定"}
    nodes = [s["station"] for s in model["stations"]]
    mk = [r["makespan"] for r in ok]
    ct = [r["makespan"] / n_sets for r in ok]
    first = [r["first_out"] for r in ok]
    steady = [(r["makespan"] - r["first_out"]) / (n_sets - 1) for r in ok] if n_sets > 1 else []
    bott_count: dict[str, int] = defaultdict(int)
    for r in ok:
        bott_count[max(nodes, key=lambda s: r["stations"][s]["util"])] += 1
    bottleneck = max(bott_count, key=bott_count.get)
    # 理論下限：最慢的站（平均作業時間 ÷ 人數）決定每組最少要多久
    eff = {s: (sum(model["times"][s]) / len(model["times"][s]) * factor.get(s, 1.0)) / max(1, servers.get(s, 1))
           for s in nodes}
    bound_st = max(nodes, key=lambda s: eff[s])

    stations = []
    for s in nodes:
        u = [r["stations"][s]["util"] * 100 for r in ok]
        b = [r["stations"][s]["blocked"] * 100 for r in ok]
        w = [r["stations"][s]["starved"] * 100 for r in ok]
        stations.append({"station": s, "util_pct": round(sum(u) / len(u), 1), "blocked_pct": round(sum(b) / len(b), 1),
                         "starved_pct": round(sum(w) / len(w), 1),
                         "bottleneck_share_pct": round(bott_count.get(s, 0) / len(ok) * 100, 1),
                         "factor": factor.get(s, 1.0), "servers": max(1, servers.get(s, 1)),
                         "eff_time": round(eff[s], 1)})
    buffers = []
    for name in ok[0]["buffers"]:
        a = [r["buffers"][name]["avg"] for r in ok]
        buffers.append({"buffer": name, "avg_wip": round(sum(a) / len(a), 2),
                        "max_wip": max(r["buffers"][name]["max"] for r in ok),
                        "limit": cap.get(name.split("→")[1])})
    return {
        "ok": True, "group_id": model["group_id"], "round": model["round"], "round_label": model["round_label"],
        "params": {"n_sets": n_sets, "reps": reps, "seed": seed, "mode": mode, "wip": wip,
                   "factor": factor, "servers": servers},
        "completed_reps": len(ok),
        "makespan_sec": _summ(mk), "line_ct_sec": _summ(ct), "first_out_sec": _summ(first),
        "steady_sec": _summ(steady) if steady else None,
        "throughput_per_hr": round(3600 / (sum(ct) / len(ct)), 1),
        "bottleneck": bottleneck, "bottleneck_share_pct": round(bott_count[bottleneck] / len(ok) * 100, 1),
        "bound_station": bound_st, "bound_ct_sec": round(eff[bound_st], 1),
        "stations": stations, "buffers": buffers,
        "actual": model["actual"], "flow_source": model["flow_source"],
    }
