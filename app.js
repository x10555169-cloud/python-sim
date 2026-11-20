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
  let lastRows = [];
  let lastData = null;

  // ---------- 組別、批次選擇（只影響自己的畫面；Python 仍然計算全部） ----------
  const GROUP_COUNT = C.GROUP_COUNT || 25;
  const params = new URLSearchParams(location.search);
  const loadPref = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
  const savePref = (k, v) => { try { localStorage.setItem(k, v); } catch {} };
  let selected = (params.get("group") || loadPref("sim-group") || "ALL").toUpperCase();
  let selBatch = (params.get("batch") || loadPref("sim-batch") || "ALL").toUpperCase();
  const baseGroups = Array.from({ length: GROUP_COUNT }, (_, i) => `G${String(i + 1).padStart(2, "0")}`);
  const batchLabel = (b) => (b === "FORMAL" ? "正式" : b);
  const sortBatch = (a, b) => (a === "FORMAL") - (b === "FORMAL") || a.localeCompare(b, "en", { numeric: true });

  function setOptions(id, html) {
    if ($(id).dataset.html !== html) { $(id).innerHTML = html; $(id).dataset.html = html; }
  }

  function buildOptions() {
    const lines = lastData?.lines || [];
    // 組別選單：筆數依「目前選的批次」計算
    const gCount = {};
    lines.filter((l) => selBatch === "ALL" || l.batch === selBatch)
      .forEach((l) => (gCount[l.group_id] = (gCount[l.group_id] || 0) + l.events));
    const gIds = [...new Set([...baseGroups, ...lines.map((l) => l.group_id)])].sort();
    if (selected !== "ALL" && !gIds.includes(selected)) gIds.push(selected);
    setOptions("groupSel", [`<option value="ALL">全部組別</option>`].concat(gIds.map((g) =>
      `<option value="${esc(g)}">${esc(g)}${gCount[g] ? `（${gCount[g]} 筆）` : "（無資料）"}</option>`)).join(""));
    $("groupSel").value = selected;

    // 批次選單：依資料自動產生；筆數依「目前選的組別」計算
    const bCount = {};
    lines.filter((l) => selected === "ALL" || l.group_id === selected)
      .forEach((l) => (bCount[l.batch] = (bCount[l.batch] || 0) + l.events));
    const bIds = [...new Set(lines.map((l) => l.batch))].sort(sortBatch);
    if (selBatch !== "ALL" && !bIds.includes(selBatch)) bIds.push(selBatch);
    setOptions("batchSel", [`<option value="ALL">全部批次</option>`].concat(bIds.map((b) =>
      `<option value="${esc(b)}">${esc(batchLabel(b))}${bCount[b] ? `（${bCount[b]} 筆）` : "（無資料）"}</option>`)).join(""));
    $("batchSel").value = selBatch;
  }

  function onFilterChange() {
    selected = $("groupSel").value;
    selBatch = $("batchSel").value;
    savePref("sim-group", selected);
    savePref("sim-batch", selBatch);
    const u = new URL(location.href);
    selected === "ALL" ? u.searchParams.delete("group") : u.searchParams.set("group", selected);
    selBatch === "ALL" ? u.searchParams.delete("batch") : u.searchParams.set("batch", selBatch);
    history.replaceState(null, "", u);
    renderView();
  }
  $("groupSel").onchange = onFilterChange;
  $("batchSel").onchange = onFilterChange;

  function renderLines(lines, st, emptyText) {
    const head = ["組別", "批次", "完成件數", "在製品", "瓶頸站", "平衡率", "產出/小時", "經過(分)", ...st];
    const body = lines.length ? lines.map((l) => {
      const cells = st.map((s) => {
        const v = l.avg_ct[s];
        return `<td class="${s === l.bottleneck ? "bn" : ""}">${v ?? "—"}</td>`;
      }).join("");
      return `<tr><td>${esc(l.group_id)}</td><td>${esc(batchLabel(l.batch))}</td><td>${l.finished}</td><td>${l.wip}</td>`
        + `<td>${esc(l.bottleneck)}（${l.bottleneck_ct}s）</td><td>${l.balance_pct}%</td>`
        + `<td>${l.throughput_per_hr}</td><td>${l.elapsed_min}</td>${cells}</tr>`;
    }).join("") : `<tr><td class="empty" colspan="${head.length}">${esc(emptyText)}</td></tr>`;
    $("lines").innerHTML = `<thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${body}</tbody>`;
  }

  const tilesHtml = (tiles) => tiles.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");

  function renderView() {
    buildOptions();
    const top = lastRows[0];
    const d = lastData;
    if (!top) return;
    const allG = selected === "ALL";
    const allB = selBatch === "ALL";
    const scope = [allG ? "" : selected, allB ? "" : batchLabel(selBatch)].filter(Boolean).join(" ");
    $("linesTitle").textContent = scope ? `${scope} 生產線分析` : "各組生產線分析";

    if (!d) { $("latest").textContent = top.message; return; }
    const lines = d.lines.filter((l) => (allG || l.group_id === selected) && (allB || l.batch === selBatch));
    const t = new Date(top.created_at || Date.now()).toLocaleTimeString("zh-TW", { hour12: false, timeZone: "Asia/Taipei" });
    const sum = (k) => lines.reduce((a, l) => a + (l[k] || 0), 0);
    // 排名：選了批次 → 跟同一批次的各組比；沒選 → 跟全部「組別＋批次」比
    const pool = d.lines.filter((l) => allB || l.batch === selBatch);
    const ranked = [...pool].sort((a, b) => b.throughput_per_hr - a.throughput_per_hr);
    const rankOf = (l) => `${ranked.indexOf(l) + 1}/${ranked.length}`;

    const u = new URL(location.href);
    $("groupInfo").textContent = scope ? `分享這個畫面：${u.origin}${u.pathname}${u.search}` : `共 ${d.groups} 組有資料`;

    if (!lines.length) {
      $("latest").textContent = `${scope} 目前沒有資料（Python 第 ${top.tick ?? "—"} 次執行時）`;
      $("latestStats").innerHTML = "";
    } else if (allG && allB) {
      $("latest").textContent = top.message;
      const avgBal = (sum("balance_pct") / lines.length).toFixed(1);
      $("latestStats").innerHTML = tilesHtml([["事件筆數", d.events], ["組數", d.groups], ["工站數", d.stations.length],
        ["產出率最高", `${d.best.group_id}（${d.best.throughput_per_hr}/hr）`], ["平均平衡率", `${avgBal}%`]]);
    } else if (allG) {
      // 全部組別、單一批次：比較各組
      const best = ranked[0];
      const avgBal = (sum("balance_pct") / lines.length).toFixed(1);
      $("latest").textContent = `[${t}] ${batchLabel(selBatch)}：共 ${lines.length} 組，產出率最高 ${best.group_id}（每小時 ${best.throughput_per_hr} 件），平均平衡率 ${avgBal}%`;
      $("latestStats").innerHTML = tilesHtml([["事件筆數", sum("events")], ["組數", lines.length], ["完成件數", sum("finished")],
        ["產出率最高", `${best.group_id}（${best.throughput_per_hr}/hr）`], ["平均平衡率", `${avgBal}%`]]);
    } else {
      // 單一組別（全部或單一批次）
      const parts = lines.map((l) =>
        `${batchLabel(l.batch)} 完成 ${l.finished} 件、瓶頸 ${l.bottleneck}（${l.bottleneck_ct} 秒）、平衡率 ${l.balance_pct}%、每小時 ${l.throughput_per_hr} 件（排名 ${rankOf(l)}）`);
      $("latest").textContent = `[${t}] ${selected}：${parts.join("；")}`;
      const worst = lines.reduce((a, l) => (l.bottleneck_ct > a.bottleneck_ct ? l : a));
      $("latestStats").innerHTML = tilesHtml([["事件筆數", sum("events")], allB ? ["批次數", lines.length] : ["排名", rankOf(lines[0])],
        ["完成件數", sum("finished")], ["在製品", sum("wip")], ["最慢工站", `${worst.bottleneck}（${worst.bottleneck_ct}s）`]]);
    }
    renderLines(lines, d.stations || [], `${scope} 目前沒有資料`);
  }

  function renderResults(rows) {
    if (!rows || !rows.length || rows[0].id === lastTopId) return;
    lastTopId = rows[0].id;
    lastRows = rows;
    const withData = rows.find((r) => r.data && r.data.lines);
    if (withData) lastData = withData.data;
    renderView();
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
