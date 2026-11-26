"""用經驗分布（Empirical Distribution）模擬產線：以「已完成」的實際加工時間，預測產線表現、比較不同方案。

跟 simulation.py 的差別：
  simulation.py  統計分析：把「已經發生」的紀錄整理成 CT、瓶頸、產線 Cycle Time
  des.py         模擬：每站的加工時間用經驗分布產生，讓電腦依流程「假裝生產」很多次，預測結果

一、加工時間：經驗分布（不假設常態、指數等理論分布，直接用實際資料的分布）
  連續型（預設，Law & Kelton 的分段線性經驗分布）
      把 n 筆資料由小到大排好 x(1)…x(n)，相鄰兩點之間用直線連成累積分布；
      抽樣（反函數法）：U ~ 均勻(0,1)，P = (n−1)U，I = ⌊P⌋ + 1，
                        加工時間 = x(I) + (P − I + 1) × (x(I+1) − x(I))
      → 會產生資料點「之間」的值，資料少時比只重抽原始值合理；不會超出最小～最大值
  離散型（重抽樣）  每筆資料被抽中的機率都是 1/n，只會抽到出現過的值
  固定平均值        每件都用平均值（沒有波動，給教學比較用）

二、資料來源（只用 status = COMPLETED 的已完成資料）：實務上每站至少 30 筆、最好 100 筆以上，
  但一場只做 3～5 張椅子，所以可以選擇加入之前的資料：
  round   只用本場（即時：做完幾件就用幾筆）
  group   本場 + 本組其他場次
  class   本場 + 全班所有組的同一站
  auto30  自動補到 30 筆：本場 → 不夠再加本組其他場次 → 還不夠再加全班同一站

三、產線模型（每一組 + 每一個場次）：
  工站與流程   station_flow（同老師的候選順序 T3 → T2 → T1 → 組別）；沒有流程時：
               有 ST09 → 老師網頁預設的 9 站組裝流程；否則依工站編號串聯
  合流（組裝） 有好幾個前站的工站，要每個前站各送來 1 件才能開工（齊套）
  起點站       原料無限，最多投入 N 件（N = 要生產的組數）
  站間緩衝區   上限 = station_wip 的「下一站_LIMIT」，沒設定用 2（同老師網頁）；可改成不限制
  阻塞         做完時下一站的緩衝區滿了 → 拿著成品等（佔住人手），直到有空位
  人數         每站幾個人（同時能做幾件），預設 1
  結束         終點站完成 N 組
  一次模擬 = 一次假想的生產（事件驅動：時間直接跳到下一個「某站做完」的時刻）；
  重複 R 次（亂數不同），取平均與 90% 範圍（第 5～95 百分位）。

只用 Python 內建模組，可以在瀏覽器（Pyodide）裡執行。
"""
from __future__ import annotations

import heapq
import random
from collections import defaultdict, deque

from simulation import analyze_line, edges_of, flow_for, round_label, round_of, round_sort_key, terminal_station

DEFAULT_WIP_LIMIT = 2
MIN_SAMPLES = 30     # 實務起點
GOOD_SAMPLES = 100   # 理想
DEFAULT_FLOW_9 = [("ST01", "ST05"), ("ST02", "ST05"), ("ST03", "ST06"), ("ST04", "ST06"),
                  ("ST05", "ST07"), ("ST06", "ST07"), ("ST07", "ST08"), ("ST08", "ST09")]
SOURCE_LABEL = {"round": "只用本場已完成資料", "group": "本場 + 本組其他場次",
                "class": "本場 + 全班同一站", "auto30": f"自動補到 {MIN_SAMPLES} 筆（本場 → 本組 → 全班）"}


# ---------------------------------------------------------------- 1. 經驗分布
def empirical_continuous(sorted_vals: list[float], u: float) -> float:
    """連續型經驗分布（分段線性）的反函數：u ∈ [0,1) → 加工時間。sorted_vals 要先由小到大排好。"""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    p = (n - 1) * u
    i = min(int(p), n - 2)          # 程式的索引從 0 開始：i = I − 1
    return sorted_vals[i] + (p - i) * (sorted_vals[i + 1] - sorted_vals[i])


def empirical_discrete(vals: list[float], u: float) -> float:
    """離散型經驗分布（重抽樣）：每筆機率 1/n。"""
    return vals[min(int(u * len(vals)), len(vals) - 1)]


def level_of(n: int) -> dict:
    """資料量等級：<10 僅供參考、10~29 初步、30 以上達實務起點、100 以上理想"""
    if n >= GOOD_SAMPLES:
        return {"code": "best", "label": f"≥{GOOD_SAMPLES} 理想"}
    if n >= MIN_SAMPLES:
        return {"code": "ok", "label": f"≥{MIN_SAMPLES} 實務起點"}
    if n >= 10:
        return {"code": "low", "label": "10~29 初步參考"}
    return {"code": "few", "label": "<10 僅供參考"}


def _quart(v: list[float]) -> dict:
    v = sorted(v)
    q = lambda p: round(empirical_continuous(v, p), 1) if v else None   # 分位數也用分段線性
    return {"n": len(v), "mean": round(sum(v) / len(v), 1) if v else None, "min": v[0] if v else None,
            "p25": q(0.25), "median": q(0.5), "p75": q(0.75), "max": v[-1] if v else None}


# ---------------------------------------------------------------- 2. 建立模型
def _durations(rows: list[dict], station: str) -> list[float]:
    out = []
    for r in rows:
        if (r.get("station_id") or "").strip() == station:
            try:
                d = float(r.get("duration_sec") or 0)
            except (TypeError, ValueError):
                d = 0
            if d > 0:
                out.append(d)
    return out


def build_model(events: list[dict], flows: list[dict], limits: list[dict], group: str, rnd: str,
                source: str = "round") -> dict:
    """從資料庫的資料建立某組某場次的模型（工站、流程、各站經驗分布、緩衝區上限、實際結果）。"""
    source = source if source in SOURCE_LABEL else "round"
    done = [e for e in events if (e.get("status") or "COMPLETED") == "COMPLETED"]
    rows = [e for e in done if (e.get("group_id") or "").strip() == group and round_of(e.get("product_id")) == rnd]
    if not rows:
        return {"ok": False, "error": f"{group} {round_label(rnd)} 還沒有完工紀錄，無法建立模型"}
    # 加入的資料：本組其他場次（場次近的優先）、全班其他組
    group_other = sorted((e for e in done if (e.get("group_id") or "").strip() == group
                          and round_of(e.get("product_id")) != rnd),
                         key=lambda e: abs(round_sort_key(round_of(e.get("product_id"))) - round_sort_key(rnd)))
    class_other = [e for e in done if (e.get("group_id") or "").strip() != group]

    flows_by_key: dict[str, list[dict]] = defaultdict(list)
    for f in flows or []:
        flows_by_key[(f.get("group_id") or "").strip()].append(f)
    key, flow = flow_for(flows_by_key, group, rnd)
    real_edges = edges_of(flow)
    with_data = sorted({(r.get("station_id") or "").strip() for r in rows if _durations([r], (r.get("station_id") or "").strip())})

    if real_edges:
        edges = [(a, b) for a, b in real_edges if b]
        flow_src = f"老師設定的流程（station_flow：{key}）"
    elif "ST09" in with_data:
        edges = list(DEFAULT_FLOW_9)
        flow_src = "沒有設定流程 → 用老師網頁預設的 9 站組裝流程"
    else:
        edges = list(zip(with_data, with_data[1:]))
        flow_src = "沒有設定流程 → 依工站編號串聯"
    nodes = sorted({a for a, _ in edges} | {b for _, b in edges} | (set() if edges else set(with_data)))
    preds = {s: sorted(a for a, b in edges if b == s) for s in nodes}
    succs = {s: sorted(b for a, b in edges if a == s) for s in nodes}
    terminal = terminal_station([(a, b) for a, b in edges] + [(s, "") for s in nodes if not succs[s]])

    # 各站的經驗分布資料：本場 + 依「資料來源」加入的資料
    times: dict[str, list[float]] = {}
    stations = []
    lim = _wip_limits(limits, group, rnd)
    for s in nodes:
        own = _durations(rows, s)
        grp = _durations(group_other, s)
        cls = _durations(class_other, s)
        added, used = [], ["本場"]
        if source == "group" or (source == "auto30" and len(own) < MIN_SAMPLES):
            added += grp
            if grp:
                used.append("本組其他場次")
        if source == "class" or (source == "auto30" and len(own) + len(added) < MIN_SAMPLES):
            added += cls
            if cls:
                used.append("全班同一站")
        pool = own + added
        times[s] = sorted(pool)
        o, a = _quart(own), _quart(added)
        diff = (abs(a["mean"] - o["mean"]) / o["mean"] * 100) if own and added and o["mean"] else None
        stations.append({
            "station": s, "preds": preds[s], "succs": succs[s],
            "own": o, "added": a, "pool": _quart(pool), "used": used if added else ["本場"],
            "level": level_of(len(pool)),
            "diff_pct": round(diff, 0) if diff is not None else None,
            "diff_warn": diff is not None and diff > 30 and len(own) >= 3,   # 加入的資料平均差超過 30%：合併前要確認做法相同
            "no_data": not pool,
            "wip_limit_in": lim.get(s, DEFAULT_WIP_LIMIT) if preds[s] else None,
            "cdf": [round(x, 1) for x in sorted(pool)] if len(pool) <= 300 else
                   [round(empirical_continuous(sorted(pool), i / 100), 1) for i in range(101)],
        })
    # 完全沒有資料的工站（流程有、但還沒做到、也沒有可加入的資料）：暫用全部資料中位數
    all_t = sorted(t for v in times.values() for t in v)
    median = all_t[len(all_t) // 2] if all_t else 1.0
    missing = [s for s in nodes if not times[s]]
    for s in missing:
        times[s] = [median]

    actual = analyze_line(rows, real_edges)
    return {
        "ok": True, "group_id": group, "round": rnd, "round_label": round_label(rnd),
        "source": source, "source_label": SOURCE_LABEL[source],
        "flow_source": flow_src, "edges": [list(e) for e in edges], "terminal": terminal,
        "roots": [s for s in nodes if not preds[s]], "stations": stations, "times": times,
        "wip_limits": {s: lim.get(s, DEFAULT_WIP_LIMIT) for s in nodes if preds[s]},
        "wip_limit_source": "station_wip 的 _LIMIT 設定" if lim else f"沒有設定 → 預設 {DEFAULT_WIP_LIMIT}",
        "missing_data": missing, "ignored_stations": [s for s in with_data if s not in nodes],
        "min_samples": min((len(times[s]) for s in nodes if s not in missing), default=0),
        "actual": {k: actual[k] for k in ("output_sets", "total_sec", "takt_sec", "steady_sec", "bottleneck",
                                          "bottleneck_ct", "terminal_reached", "output_station", "events")},
    }


def _wip_limits(limits: list[dict], group: str, rnd: str) -> dict[str, int]:
    """station_wip 的「ST05_LIMIT」= 送進 ST05 的緩衝區上限（同老師網頁 ApiFlow；0 或空白 = 沒設定）"""
    lim: dict[str, int] = {}
    for want in (f"{group}-OFFICIAL" if rnd == "FORMAL" else f"{group}-T{rnd[4:]}", group):
        for r in limits or []:
            sid = (r.get("station_id") or "").strip()
            if (r.get("group_id") or "").strip() == want and sid.endswith("_LIMIT"):
                try:
                    v = int(float(r.get("input_wip")))
                except (TypeError, ValueError):
                    v = 0
                lim.setdefault(sid[:-6], v if v > 0 else DEFAULT_WIP_LIMIT)
        if lim:
            break
    return lim


# ---------------------------------------------------------------- 3. 模擬引擎（一次假想的生產）
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
        """從這站的經驗分布抽一個加工時間，再乘上作業時間倍率"""
        if self.mode == "mean":
            base = self.mean[s]
        elif self.mode == "disc":
            base = empirical_discrete(self.times[s], self.rng.random())
        else:
            base = empirical_continuous(self.times[s], self.rng.random())
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


# ---------------------------------------------------------------- 4. 重複模擬、統計
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


def simulate(model: dict, n_sets: int = 10, reps: int = 200, seed: int = 2026, mode: str = "cont",
             factor: dict | None = None, servers: dict | None = None, wip: str | int = "db") -> dict:
    """跑 reps 次模擬。wip："db" = 資料庫設定（沒有用 2）；整數 = 全部緩衝區同一個上限；"none" = 不限制。"""
    if not model.get("ok"):
        return model
    mode = {"sample": "disc"}.get(mode, mode) if mode in ("cont", "disc", "mean", "sample") else "cont"
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
        "data_source": model["source_label"], "min_samples": model["min_samples"],
        "samples": {st["station"]: st["pool"]["n"] for st in model["stations"]},
    }
