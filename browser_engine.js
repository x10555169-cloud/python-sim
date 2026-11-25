// 瀏覽器版後端（不用 Render）：
//   1. 用 API（Supabase REST）直接從瀏覽器讀資料庫：event、station_flow、station_wip（只讀，不寫入）
//   2. 用 Pyodide 在瀏覽器裡執行 Python：simulation.py 原封不動（跟 Render 上跑的是同一個檔案）
//   3. 每 5 秒檢查一次，有新資料才重新計算（跟 Render 的 main.py 一樣）
// app.js 在 MODE = "browser" 時使用；開始／暫停／繼續／停止只影響自己這個瀏覽器分頁。
(() => {
  const C = window.APP_CONFIG || {};
  const SB = (C.SUPABASE_URL || "").replace(/\/$/, "");
  const KEY = C.SUPABASE_KEY || "";
  const INTERVAL_MS = (C.SIM_INTERVAL_SECONDS || 5) * 1000;
  const PYODIDE_URL = C.PYODIDE_URL || "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  const EVENT_COLUMNS = "id,group_id,product_id,station_id,start_time,finish_time,duration_sec,wip_before_start,wip_after_finish,status";

  // ---------- 1. API：從瀏覽器讀資料庫 ----------
  const headers = { apikey: KEY, Authorization: `Bearer ${KEY}` };
  async function getAll(path) {           // Supabase 一次最多回 1000 筆：分頁讀到完
    const out = [];
    for (let offset = 0; ; offset += 1000) {
      const r = await fetch(`${SB}/rest/v1/${path}&limit=1000&offset=${offset}`, { headers });
      if (!r.ok) throw new Error(`讀取 ${path.split("?")[0]} 失敗（HTTP ${r.status}）`);
      const rows = await r.json();
      out.push(...rows);
      if (rows.length < 1000) return out;
    }
  }
  async function getOptional(path) {      // 表不存在時回傳空清單（同 database.py）
    try { return await getAll(path); } catch { return []; }
  }
  const fetchEvents = () => getAll(`event?select=${EVENT_COLUMNS}&order=finish_time.asc.nullslast,id.asc`);
  const fetchFlows = () => getOptional("station_flow?select=group_id,station_id,next_station_id&order=id.asc");
  const fetchModes = () => getOptional("station_wip?select=group_id,station_id,input_wip,updated_at&station_id=in.(GROUP_MODE,SYSTEM_MODE)");

  // ---------- 2. Python（Pyodide） ----------
  let pyReady = null;
  function loadPython() {
    if (pyReady) return pyReady;
    pyReady = (async () => {
      if (!window.loadPyodide) {
        await new Promise((ok, fail) => {
          const s = document.createElement("script");
          s.src = PYODIDE_URL + "pyodide.js";
          s.onload = ok;
          s.onerror = () => fail(new Error("Python（Pyodide）下載失敗，請檢查網路後重新整理"));
          document.head.appendChild(s);
        });
      }
      const py = await window.loadPyodide({ indexURL: PYODIDE_URL });
      const src = await (await fetch(`simulation.py?t=${Date.now()}`)).text();
      py.FS.writeFile("simulation.py", src);
      py.runPython(`
import json, sys
sys.path.insert(0, ".")
from simulation import compute
def run_compute(tick, events_json, flows_json, modes_json):
    message, data = compute(int(tick), json.loads(events_json), json.loads(flows_json), json.loads(modes_json))
    return json.dumps({"message": message, "data": data}, ensure_ascii=False, default=str)
`);
      const fn = py.globals.get("run_compute");
      return { version: py.version, compute: (tick, ev, fl, md) => JSON.parse(fn(tick, JSON.stringify(ev), JSON.stringify(fl), JSON.stringify(md))) };
    })();
    pyReady.catch(() => { pyReady = null; });
    return pyReady;
  }

  // ---------- 3. 模擬迴圈（同 main.py：開始 / 暫停 / 繼續 / 停止） ----------
  const results = [];   // 最新的在前面，最多保留 30 筆
  const status = { running: false, paused: false, tick: 0, run_id: null, last_check_at: null, last_check: "", message: "" };
  let timer = null, lastSig = null, checked = 0, nextId = 1, busy = false;
  const nowIso = () => new Date().toISOString();
  const runIdNow = () => { const d = new Date(Date.now() + 8 * 3600e3); return d.toISOString().slice(5, 16).replace(/[-T:]/g, (c) => (c === "T" ? "-" : "")); };
  function addResult(r) {
    results.unshift({ id: nextId++, created_at: nowIso(), ...r });
    results.length = Math.min(results.length, 30);
  }

  async function step(force = false) {
    if (busy) return;
    busy = true;
    try {
      const [events, flows, modes] = await Promise.all([fetchEvents(), fetchFlows(), fetchModes()]);
      // 指紋：筆數、最晚完工時間、流程、目前場次——有任何改變才重新計算
      const sig = JSON.stringify([events.length, events.reduce((m, e) => (String(e.finish_time) > m ? String(e.finish_time) : m), ""), flows, modes]);
      checked += 1;
      if (!force && sig === lastSig) {
        status.last_check_at = nowIso();
        status.last_check = `第 ${checked} 次檢查：${events.length} 筆，沒有新資料`;
        return;
      }
      const py = await loadPython();
      lastSig = sig;
      const tick = force && !status.running ? 0 : ++status.tick;
      let { message, data } = py.compute(tick, events, flows, modes);
      if (tick === 0) message = message.replace("第 0 次執行", "打開網頁時的資料快照");
      addResult({ run_id: status.run_id || "snapshot", tick, message, data });
      status.message = message;
      status.last_check_at = nowIso();
      status.last_check = `第 ${checked} 次檢查：${events.length} 筆，${tick === 0 ? "已計算一次" : "有新資料 → 已重新計算"}`;
    } catch (e) {
      status.message = `錯誤：${e.message}`;
      status.last_check_at = nowIso();
      status.last_check = `錯誤：${e.message}`;
      throw e;
    } finally {
      busy = false;
    }
  }
  function loop() {
    clearInterval(timer);
    timer = setInterval(() => step().catch(() => {}), INTERVAL_MS);
  }

  window.BrowserEngine = {
    pythonInfo: () => (pyReady ? "載入中或已載入" : "尚未載入"),
    loadPython,
    // 打開網頁先算一次（跟 Render 的 startup_snapshot 一樣），不算在執行次數裡
    async snapshot() { if (!results.length) await step(true); },
    async status() { return { ...status }; },
    async results(limit = 30) { return results.slice(0, limit); },
    async start() {
      if (status.running) return { ok: true, already_running: true };
      Object.assign(status, { running: true, paused: false, tick: 0, run_id: runIdNow() });
      lastSig = null; checked = 0;
      addResult({ run_id: status.run_id, tick: 0, message: "Hello from Python！模擬已啟動（Python 在你的瀏覽器裡執行，不經過 Render）" });
      await step().catch(() => {});   // 錯誤會寫在狀態裡，迴圈照樣繼續（同 main.py）
      loop();
      return { ok: true, run_id: status.run_id };
    },
    async pause() {
      if (!status.running) throw new Error("模擬沒有在執行");
      clearInterval(timer);
      Object.assign(status, { running: false, paused: true });
      return { ok: true, tick: status.tick };
    },
    async resume() {
      if (!status.paused) throw new Error("模擬沒有暫停");
      Object.assign(status, { running: true, paused: false });
      lastSig = null;
      await step().catch(() => {});
      loop();
      return { ok: true, tick: status.tick };
    },
    async stop() {
      clearInterval(timer);
      Object.assign(status, { running: false, paused: false });
      return { ok: true };
    },
  };
})();
