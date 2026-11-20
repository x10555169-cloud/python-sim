// 前端：讀取 Python 送出的結果並顯示；api / supabase 模式可開始／停止模擬
(() => {
  const C = window.APP_CONFIG || {};
  const MODE = C.MODE || "static";
  const API = (C.API_BASE || "").replace(/\/$/, "");
  const SB = (C.SUPABASE_URL || "").replace(/\/$/, "");
  const $ = (id) => document.getElementById(id);
  const tokenKey = "sim-admin-token";
  const SOURCE_LABEL = { static: "GitHub Actions（Python）", api: "FastAPI", supabase: "Supabase" };

  try { $("token").value = localStorage.getItem(tokenKey) || ""; } catch {}
  $("stSource").textContent = SOURCE_LABEL[MODE] || MODE;
  if (MODE === "static") {
    ["btnStart", "btnPause", "btnResume", "btnStop", "token"].forEach((id) => ($(id).hidden = true));
    $("apiMsg").textContent = "靜態模式：每次 push 到 GitHub，Actions 會重新執行 Python 並更新這頁。";
  }

  // ---------- 讀資料 ----------
  async function sbGet(path) {
    const r = await fetch(`${SB}/rest/v1/${path}`, { headers: { apikey: C.SUPABASE_KEY } });
    if (!r.ok) throw new Error(`Supabase ${r.status}: ${await r.text()}`);
    return r.json();
  }
  async function apiCall(path, opts = {}) {
    const r = await fetch(`${API}${path}`, opts);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || `API ${r.status}`);
    return body;
  }
  async function load() {
    if (MODE === "static") {
      const d = await (await fetch(`data/results.json?t=${Date.now()}`)).json();
      return { rows: d.results, st: d.status, generatedAt: d.generated_at };
    }
    if (MODE === "supabase") {
      const [rows, st] = await Promise.all([
        sbGet("sim_results?select=*&order=id.desc&limit=30"),
        sbGet("sim_status?select=*&id=eq.1"),
      ]);
      return { rows, st: st[0] || {} };
    }
    const [rows, st] = await Promise.all([apiCall("/results?limit=30"), apiCall("/status")]);
    return { rows, st };
  }

  // ---------- 畫面 ----------
  const fmtTime = (iso) => iso ? new Date(iso).toLocaleString("zh-TW", { hour12: false, timeZone: "Asia/Taipei" }) : "";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let lastTopId = null;

  function renderLines(d) {
    const lines = d.lines || [];
    const st = d.stations || [];
    const head = ["組別", "批次", "完成件數", "在製品", "瓶頸站", "平衡率", "產出/小時", "經過(分)", ...st];
    const body = lines.map((l) => {
      const cells = st.map((s) => {
        const v = l.avg_ct[s];
        return `<td class="${s === l.bottleneck ? "bn" : ""}">${v ?? "—"}</td>`;
      }).join("");
      return `<tr><td>${esc(l.group_id)}</td><td>${esc(l.batch)}</td><td>${l.finished}</td><td>${l.wip}</td>`
        + `<td>${esc(l.bottleneck)}（${l.bottleneck_ct}s）</td><td>${l.balance_pct}%</td>`
        + `<td>${l.throughput_per_hr}</td><td>${l.elapsed_min}</td>${cells}</tr>`;
    }).join("");
    $("lines").innerHTML = `<thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${body}</tbody>`;
  }

  function renderResults(rows) {
    if (!rows || !rows.length || rows[0].id === lastTopId) return;
    lastTopId = rows[0].id;
    $("latest").textContent = rows[0].message;
    const d = (rows.find((r) => r.data && r.data.lines) || {}).data;
    if (d) {
      const avgBal = d.lines.length ? (d.lines.reduce((a, l) => a + l.balance_pct, 0) / d.lines.length).toFixed(1) : "—";
      const tiles = [["事件筆數", d.events], ["組數", d.groups], ["工站數", d.stations.length],
        ["產出率最高", `${d.best.group_id}（${d.best.throughput_per_hr}/hr）`], ["平均平衡率", `${avgBal}%`]];
      $("latestStats").innerHTML = tiles.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");
      renderLines(d);
    }
    $("log").innerHTML = rows.map((r) => `<li><time>${fmtTime(r.created_at)}</time>${esc(r.message)}</li>`).join("");
  }

  function renderStatus(st) {
    const state = MODE === "static" ? "done" : st.running ? "running" : st.paused ? "paused" : "stopped";
    $("stRunning").textContent = { done: "已完成", running: "執行中", paused: "已暫停", stopped: "已停止" }[state];
    $("stTick").textContent = st.tick ?? "—";
    $("stRun").textContent = st.run_id || "—";
    if (MODE !== "static") {
      $("genAt").textContent = st.last_check_at ? `最後檢查 ${fmtTime(st.last_check_at)}　${st.last_check || ""}` : "";
    }
    // 依狀態決定哪些按鈕能按：停止中 → 只能開始；執行中 → 暫停、停止；暫停中 → 繼續、停止
    $("btnStart").disabled = state !== "stopped";
    $("btnPause").disabled = state !== "running";
    $("btnResume").disabled = state !== "paused";
    $("btnStop").disabled = !(state === "running" || state === "paused");
  }

  async function refresh() {
    try {
      const { rows, st, generatedAt } = await load();
      renderResults(rows);
      renderStatus(st);
      if (generatedAt) $("genAt").textContent = `Python 執行時間：${fmtTime(generatedAt)}`;
      $("conn").textContent = "已連線"; $("conn").className = "pill ok";
    } catch (e) {
      $("conn").textContent = "連線失敗"; $("conn").className = "pill bad";
      $("apiMsg").textContent = e.message;
    }
  }

  // ---------- 開始 / 停止 ----------
  async function control(action) {
    const token = $("token").value.trim();
    try { localStorage.setItem(tokenKey, token); } catch {}
    const doing = { start: "啟動中…（Render 免費方案休眠時，第一次可能要等 30–60 秒）", pause: "暫停中…", resume: "繼續中…", stop: "停止中…" };
    $("apiMsg").textContent = doing[action];
    try {
      const res = await apiCall(`/${action}`, { method: "POST", headers: token ? { "X-Admin-Token": token } : {} });
      $("apiMsg").textContent = res.already_running ? "模擬已經在執行中" : {
        start: `已啟動，Run ID：${res.run_id}`,
        pause: `已暫停（第 ${res.tick} 次執行後），按「繼續模擬」會從這裡接著跑`,
        resume: `已繼續，從第 ${res.tick} 次之後接著跑`,
        stop: "已停止",
      }[action];
      refresh();
    } catch (e) {
      $("apiMsg").textContent = `失敗：${e.message}`;
    }
  }
  $("btnStart").onclick = () => control("start");
  $("btnPause").onclick = () => control("pause");
  $("btnResume").onclick = () => control("resume");
  $("btnStop").onclick = () => control("stop");

  refresh();
  setInterval(refresh, MODE === "static" ? 30000 : C.POLL_MS || 3000);
})();
