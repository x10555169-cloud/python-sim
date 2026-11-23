"""生產線分析（算法對齊老師的「即時監控中心」；之後要做正式模擬，只改這個檔案）。

輸入（都從 Supabase 讀，只讀不寫）：
  events  event 表：每做完一件一筆（timer.html 掃碼完工時寫入）
  flows   station_flow 表：每組每場的工站流程（station_id → next_station_id）
  modes   station_wip 表裡 GROUP_MODE / SYSTEM_MODE 列：每組「目前」在第幾場
輸出：(message, data)
  message 顯示在網頁上的一行文字
  data    各組各場的分析結果（JSON）

名詞（同老師的頁面）：
  場次      TEST1~TEST10 = 第 1~10 次測試；FORMAL = 正式實作
  Cycle Time 各站平均作業秒數
  節拍時間   該場「首件開工 → 末件完工」總耗時 ÷ 終點站產出組數
  等待時間   站內上一件完工 → 下一件開工的空檔（第一件：產線開跑 → 本站開工），只計 0~600 秒
  稼動率     作業時間 ÷（作業時間 + 等待時間）
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from collections import defaultdict
from datetime import datetime, timedelta, timezone

TW = timezone(timedelta(hours=8))
ROUND_ORDER = [f"TEST{i}" for i in range(1, 11)] + ["FORMAL"]
MAX_GAP_SEC = 600  # 同老師：超過 10 分鐘的空檔不算等待（視為休息或換場）
LONG_SPAN_SEC = 3 * 3600  # 一個場次的資料跨越超過 3 小時 → 多半混了不同天的上課資料，提醒使用者


def r1(x) -> float:
    """四捨五入到小數 1 位（用十進位精確計算，跟手算一致：81.15 → 81.2）"""
    return float(Decimal(str(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _dec(v) -> Decimal:
    return Decimal(str(v)) if v is not None and v != "" else Decimal(0)


def _dt(v) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def round_of(product_id: str) -> str:
    """產品編號 → 場次（同老師 getTestRoundFromProductId）。
    TEST2-P01 → TEST2；舊版 TEST-P01 → TEST1；P01（沒有 TEST）→ FORMAL"""
    s = str(product_id or "").strip().upper()
    m = re.match(r"^TEST(\d+)-", s)
    if m:
        return f"TEST{int(m.group(1))}"
    if s.startswith("TEST"):
        return "TEST1"
    return "FORMAL"


batch_of = round_of  # 舊名稱相容


def round_label(r: str) -> str:
    return "正式實作" if r == "FORMAL" else f"第 {r[4:]} 次測試"


def round_sort_key(r: str) -> int:
    return ROUND_ORDER.index(r) if r in ROUND_ORDER else 99


def decode_mode(input_wip) -> str | None:
    """GROUP_MODE.input_wip → 場次（同老師 decodeSystemModeInput）：1 = 正式，101~110 = 第 1~10 次測試"""
    try:
        n = int(input_wip)
    except (TypeError, ValueError):
        return None
    if n == 1:
        return "FORMAL"
    if 101 <= n <= 110:
        return f"TEST{n - 100}"
    return None


def flow_for(flows_by_key: dict[str, list[dict]], group: str, rnd: str) -> tuple[str | None, list[dict]]:
    """找這組這場用的流程（同 timer.html 的候選順序）：
    G01-T3 → G01-T2 → G01-T1 → G01；正式：G01-OFFICIAL → G01-T10 … G01-T1 → G01"""
    if rnd == "FORMAL":
        keys = [f"{group}-OFFICIAL"] + [f"{group}-T{r}" for r in range(10, 0, -1)]
    else:
        n = int(rnd[4:])
        keys = [f"{group}-T{r}" for r in range(n, 0, -1)]
    keys.append(group)
    for k in keys:
        if flows_by_key.get(k):
            return k, flows_by_key[k]
    return None, []


def edges_of(flow: list[dict]) -> list[tuple[str, str]]:
    return sorted({((f.get("station_id") or "").strip(), (f.get("next_station_id") or "").strip())
                   for f in flow if (f.get("station_id") or "").strip()})


def terminal_station(edges: list[tuple[str, str]]) -> str | None:
    """流程終點站（同老師）：沒有任何「往下一站」連線的工站；有好幾個時取編號最大的"""
    nodes = {a for a, _ in edges} | {b for _, b in edges if b}
    terminals = sorted(st for st in nodes if not any(a == st and b for a, b in edges))
    return terminals[-1] if terminals else None


def root_stations(edges: list[tuple[str, str]]) -> list[str]:
    """起點站：沒有任何前站送料進來的工站"""
    nodes = {a for a, _ in edges} | {b for _, b in edges if b}
    return sorted(st for st in nodes if not any(b == st for _, b in edges))


def analyze_line(rows: list[dict], edges: list[tuple[str, str]]) -> dict:
    """單一組別、單一場次的指標。"""
    starts_all = [d for d in (_dt(r.get("start_time")) for r in rows) if d]
    ends_all = [d for d in (_dt(r.get("finish_time")) for r in rows) if d]
    line_start = min(starts_all) if starts_all else None

    # 1. 依工站分組，依開工時間排序，算作業時間與等待時間
    by_station: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_station[(r.get("station_id") or "(未知)").strip()].append(r)
    stations = sorted(by_station)
    st_stats: dict[str, dict] = {}
    exact_avg: dict[str, Decimal] = {}   # 未四捨五入的平均 CT（瓶頸、平衡率用這個算，避免四捨五入後同分）
    exact_wait: dict[str, Decimal] = {}  # 未四捨五入的等待時間（加總時用這個，避免誤差累積）
    for st in stations:
        evs = sorted(by_station[st], key=lambda r: str(r.get("start_time")))
        run = sum((_dec(r.get("duration_sec")) for r in evs), Decimal(0))   # 十進位精確加總
        wait = Decimal(0)
        for i, r in enumerate(evs):
            cur = _dt(r.get("start_time"))
            prev = line_start if i == 0 else _dt(evs[i - 1].get("finish_time"))
            if cur and prev:
                gap = Decimal(str((cur - prev).total_seconds()))
                if 0 < gap < MAX_GAP_SEC:
                    wait += gap
        n = len(evs)
        exact_avg[st] = run / n if n else Decimal(0)
        exact_wait[st] = wait
        st_stats[st] = {
            "qty": n,
            "run_sec": r1(run),
            "avg_ct": r1(exact_avg[st]),
            "wait_sec": r1(wait),
            "avg_wait": r1(wait / n) if n else 0,
            "util_pct": r1(run / (run + wait) * 100) if run + wait > 0 else 0,
        }
    avg_ct = {st: s["avg_ct"] for st, s in st_stats.items()}

    # 2. 瓶頸站：平均 Cycle Time 最大（用未四捨五入的值比；同分取編號小的，同老師）
    bottleneck = max(stations, key=lambda st: exact_avg[st]) if stations else None
    max_exact = exact_avg.get(bottleneck, Decimal(0)) if bottleneck else Decimal(0)
    max_ct = r1(max_exact)
    balance = sum(exact_avg.values()) / (len(exact_avg) * max_exact) if max_exact else 0

    # 3. 產出：終點站的完工筆數（同老師）；終點站還沒完工時，暫用有完工的最後一站試算
    final = terminal_station(edges) or (stations[-1] if stations else None)
    if final and final in by_station:
        output_station, reached = final, True
    else:
        output_station, reached = (stations[-1] if stations else None), False
    output_evs = by_station.get(output_station, []) if output_station else []
    output_sets = len(output_evs)

    # 4. 節拍時間 = 總耗時 ÷ 產出組數；穩態間隔 = 產出站「首件完工 → 末件完工」÷（組數 − 1）
    total_sec = (max(ends_all) - min(starts_all)).total_seconds() if starts_all and ends_all else 0
    takt_exact = Decimal(str(total_sec)) / output_sets if output_sets and total_sec > 0 else None
    takt = r1(takt_exact) if takt_exact else None
    out_fin = sorted(d for d in (_dt(r.get("finish_time")) for r in output_evs) if d)
    steady = r1(Decimal(str((out_fin[-1] - out_fin[0]).total_seconds())) / (len(out_fin) - 1)) if len(out_fin) >= 2 else None

    # 5. 在製品：起點站開工的產品數 − 終點站完成的產品數
    roots = [s for s in root_stations(edges) if s in by_station] or stations[:1]
    started = {r.get("product_id") for s in roots for r in by_station[s]}
    finished = {r.get("product_id") for r in output_evs} if reached else set()

    return {
        "events": len(rows),
        "stations": stations,
        "station_stats": st_stats,
        "avg_ct": avg_ct,
        "bottleneck": bottleneck,
        "bottleneck_ct": max_ct,
        "balance_pct": r1(balance * 100),
        "final_station": final,
        "output_station": output_station,
        "terminal_reached": reached,
        "output_sets": output_sets,
        "finished": output_sets if reached else 0,
        "wip": max(len(started) - len(finished), 0),
        "total_sec": r1(total_sec),
        "elapsed_min": r1(Decimal(str(total_sec)) / 60),
        "takt_sec": takt,
        "steady_sec": steady,
        "throughput_per_hr": r1(Decimal(3600) / takt_exact) if takt_exact and reached else 0,
        "wait_sec": r1(sum(exact_wait.values(), Decimal(0))),
        "long_span": total_sec > LONG_SPAN_SEC,  # 總耗時超過 3 小時：節拍時間可能被不同天的資料拉長
        "first_start": min(starts_all).isoformat() if starts_all else None,
        "last_finish": max(ends_all).isoformat() if ends_all else None,
    }


def compute(tick: int, events: list[dict], flows: list[dict] | None = None,
            modes: list[dict] | None = None) -> tuple[str, dict]:
    now = datetime.now(TW).strftime("%H:%M:%S")
    rows = [e for e in events if (e.get("status") or "COMPLETED") == "COMPLETED"]

    # 每組「目前」場次（老師在監控中心設定的）
    current: dict[str, str] = {}
    system_round = None
    for m in modes or []:
        r = decode_mode(m.get("input_wip"))
        if m.get("station_id") == "SYSTEM_MODE":
            system_round = r
        elif m.get("station_id") == "GROUP_MODE" and r:
            current[(m.get("group_id") or "").strip()] = r

    if not rows:
        return (f"[{now}] Python 第 {tick} 次執行：event 表目前沒有資料",
                {"events": 0, "groups": 0, "stations": [], "lines": [], "best": None,
                 "current_rounds": current, "system_round": system_round})

    flows_by_key: dict[str, list[dict]] = defaultdict(list)
    for f in flows or []:
        flows_by_key[(f.get("group_id") or "").strip()].append(f)

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[((r.get("group_id") or "").strip(), round_of(r.get("product_id")))].append(r)

    lines = []
    for (g, rnd), rs in sorted(grouped.items(), key=lambda kv: (kv[0][0], round_sort_key(kv[0][1]))):
        key, flow = flow_for(flows_by_key, g, rnd)
        edges = edges_of(flow)
        lines.append({
            "group_id": g, "batch": rnd, "round_label": round_label(rnd),
            "is_current": current.get(g, system_round) == rnd,
            "flow_key": key,
            "flow": [f"{a}→{b or '終點'}" for a, b in edges],
            **analyze_line(rs, edges),
        })

    # 最佳：節拍時間最短（只比：已做到終點站、至少 2 個工站、沒有跨天資料的場次）
    done = [ln for ln in lines if ln["terminal_reached"] and ln["takt_sec"]
            and len(ln["stations"]) >= 2 and not ln["long_span"]]
    best = min(done, key=lambda ln: ln["takt_sec"]) if done else None
    data = {
        "events": len(rows),
        "groups": len({ln["group_id"] for ln in lines}),
        "stations": sorted({s for ln in lines for s in ln["stations"]}),
        "lines": lines,
        "best": ({"group_id": best["group_id"], "batch": best["batch"], "takt_sec": best["takt_sec"],
                  "throughput_per_hr": best["throughput_per_hr"]} if best else None),
        "current_rounds": current,
        "system_round": system_round,
        "has_flows": bool(flows),
    }
    msg = f"[{now}] Python 第 {tick} 次執行：讀到 {len(rows)} 筆事件、{data['groups']} 組、{len(lines)} 個場次"
    if best:
        msg += (f"；節拍時間最短為 {best['group_id']} {best['round_label']} 每組 {best['takt_sec']} 秒"
                f"（瓶頸站 {best['bottleneck']}，平均 {best['bottleneck_ct']} 秒）")
    return msg, data
