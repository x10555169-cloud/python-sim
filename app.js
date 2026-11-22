// 前端：讀取 Python 送出的結果並顯示；api / supabase 模式可開始／停止模擬
(() => {
  const C = window.APP_CONFIG || {};
  const MODE = C.MODE || "static";
  const API = (C.API_BASE || "").replace(/\/$/, "");
  const SB = (C.SUPABASE_URL || "").replace(/\/$/, "");
  const $ = (id) => document.getElementById(id);
  const tokenKey = "sim-admin-token";
  const SOURCE_LABEL = { static: "GitHub Actions（Python）", api: "FastAPI", supabase: "Supabase" };

  // 導覽列：後端連結跟著 config.js 的 API_BASE
  $("lnkBackend").href = API || "#";
  $("lnkApiDocs").href = API ? `${API}/docs` : "#";
  if (C.REPO_URL) $("lnkRepo").href = C.REPO_URL;
  if (!API) { $("lnkBackend").hidden = true; $("lnkApiDocs").hidden = true; }

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
  // ---------- 場次（同老師系統：第 1~10 次測試 + 正式實作） ----------
  const ROUNDS = [...Array.from({ length: 10 }, (_, i) => `TEST${i + 1}`), "FORMAL"];
  const roundLabel = (r) => (r === "FORMAL" ? "正式實作" : `第 ${r.slice(4)} 次測試`);
  const RESULT_LABEL = { pass: "通過", fail: "未通過" };
  let selMap = {};            // selMap[組別][場次] = 資料庫裡的一列
  let selState = "init";      // init / ok / missing（資料表還沒建）/ error / off（沒設定 Supabase）
  let selError = "";
  let roundDirty = false;     // 有沒有尚未儲存的修改
  let roundGroupShown = null; // 目前表單是哪一組
  const isSelected = (g, b) => !!(selMap[g] && selMap[g][b] && selMap[g][b].selected);

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
  const baseBatches = C.BATCHES || ["TEST1", "TEST2", "TEST3", "FORMAL"];
  const ROUNDS_ON = !!C.ENABLE_ROUND_RECORDS;   // 場次紀錄（要先在資料庫建表）；預設關閉
  const TEACHER = (C.TEACHER_SITE || "https://lctsaio365.github.io/Class_A/").replace(/\/?$/, "/");
  const batchLabel = (b) => (b === "SELECTED" ? "已選場次" : /^(TEST\d+|FORMAL)$/.test(b) ? roundLabel(b) : b);
  const sortBatch = (a, b) => (a === "FORMAL") - (b === "FORMAL") || a.localeCompare(b, "en", { numeric: true });

  // 批次篩選：全部 / 單一批次 / 只看這組已選的場次
  const matchBatch = (l) => selBatch === "ALL" || (selBatch === "SELECTED" ? isSelected(l.group_id, l.batch) : l.batch === selBatch);

  function setOptions(id, html) {
    if ($(id).dataset.html !== html) { $(id).innerHTML = html; $(id).dataset.html = html; }
  }

  function buildOptions() {
    const lines = lastData?.lines || [];
    // 組別選單：筆數依「目前選的批次」計算
    const gCount = {};
    lines.filter(matchBatch)
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
    const bIds = [...new Set([...baseBatches, ...lines.map((l) => l.batch)])].sort(sortBatch);
    if (selBatch !== "ALL" && selBatch !== "SELECTED" && !bIds.includes(selBatch)) bIds.push(selBatch);
    setOptions("batchSel", [`<option value="ALL">全部場次</option>`].concat(ROUNDS_ON ? [`<option value="SELECTED">只看已選場次</option>`] : []).concat(bIds.map((b) =>
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

  // ---------- 分析表格（算法同老師的監控中心：節拍時間 = 總耗時 ÷ 終點站產出組數） ----------
  const fmtSec = (v) => (v == null ? "—" : v >= 3600 ? `${(v / 3600).toFixed(1)} 小時` : v >= 60 ? `${(v / 60).toFixed(1)} 分` : `${v} 秒`);
  const rankable = (l) => l.terminal_reached && l.takt_sec && l.stations.length >= 2 && !l.long_span;

  function lineFlags(l) {
    const f = [];
    if (l.is_current) f.push('<span class="tag sel">進行中</span>');
    if (!l.terminal_reached) f.push(`<span class="tag warn" title="終點站 ${esc(l.final_station)} 還沒有完工紀錄">未到終點，暫以 ${esc(l.output_station)} 試算</span>`);
    if (l.long_span) f.push('<span class="tag warn" title="這一場的資料跨越超過 3 小時，可能混了不同天的上課紀錄">跨天資料</span>');
    return f.join(" ");
  }

  function renderLines(lines, st, emptyText) {
    const head = ["組別", "場次", "流程", "完成組數", "總耗時", "節拍時間（秒/組）", "瓶頸站", "平衡率", "等待合計", "在製品", ...st.map((x) => `${x} CT`)];
    const body = lines.length ? lines.map((l) => {
      const cells = st.map((s) => `<td class="${s === l.bottleneck ? "bn" : ""}">${l.avg_ct[s] ?? "—"}</td>`).join("");
      const flow = l.flow && l.flow.length ? esc(l.flow.join("、")) : '<span class="muted" title="老師的系統裡沒有這場的流程設定，用有資料的最後一站當終點">未設定</span>';
      return `<tr class="${l.is_current ? "cur" : ""}"><td>${esc(l.group_id)}</td><td>${esc(batchLabel(l.batch))} ${lineFlags(l)}</td>`
        + `<td class="flow">${flow}</td><td>${l.output_sets}</td><td>${fmtSec(l.total_sec)}</td><td><b>${l.takt_sec ?? "—"}</b></td>`
        + `<td>${esc(l.bottleneck)}（${l.bottleneck_ct}s）</td><td>${l.balance_pct}%</td><td>${fmtSec(l.wait_sec)}</td><td>${l.wip}</td>${cells}</tr>`;
    }).join("") : `<tr><td class="empty" colspan="${head.length}">${esc(emptyText)}</td></tr>`;
    $("lines").innerHTML = `<thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${body}</tbody>`;
  }

  // 單一組別 + 單一場次：各工站明細（同老師監控中心的統計表）
  function renderStations(line) {
    const box = $("stationBox");
    if (!line) { box.hidden = true; return; }
    box.hidden = false;
    $("stationTitle").textContent = `${line.group_id} ${batchLabel(line.batch)} 各工站明細`;
    const rows = Object.entries(line.station_stats).map(([st, s]) =>
      `<tr class="${st === line.bottleneck ? "hl" : ""}"><td>${esc(st)}${st === line.bottleneck ? ' <span class="tag fail">瓶頸</span>' : ""}${st === line.final_station ? ' <span class="tag sel">終點</span>' : ""}</td>`
      + `<td>${s.qty}</td><td>${s.avg_ct}</td><td>${line.takt_sec ? Math.round(s.avg_ct / line.takt_sec * 100) + "%" : "—"}</td>`
      + `<td>${s.run_sec}</td><td>${s.avg_wait}</td><td>${s.wait_sec}</td><td>${s.util_pct}%</td></tr>`).join("");
    $("stationTable").innerHTML = `<thead><tr><th>工站</th><th>筆數</th><th>平均 Cycle Time（秒）</th><th>佔節拍時間</th>`
      + `<th>總作業時間（秒）</th><th>平均等待（秒）</th><th>總等待（秒）</th><th>稼動率</th></tr></thead><tbody>${rows}</tbody>`;
    $("stationNote").textContent = `節拍時間 ${line.takt_sec ?? "—"} 秒/組 = 總耗時 ${line.total_sec} 秒 ÷ ${line.output_station} 產出 ${line.output_sets} 組`
      + (line.steady_sec ? `；排除首件暖線的穩態產出間隔 ${line.steady_sec} 秒/組` : "");
  }

  const tilesHtml = (tiles) => tiles.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");

  function renderTeacherLinks() {
    const el = $("teacherLinks");
    if (selected === "ALL") { el.innerHTML = `<a href="${TEACHER}" target="_blank" rel="noopener">老師的監控系統</a>`; return; }
    const g = encodeURIComponent(selected);
    const cur = lastData?.current_rounds?.[selected] || lastData?.system_round;
    el.innerHTML = (cur ? `<span class="tag sel">${esc(selected)} 目前：${esc(roundLabel(cur))}</span> ` : "")
      + `<a href="${TEACHER}${encodeURIComponent("工蓋螢幕.html")}?group=${g}" target="_blank" rel="noopener">${esc(selected)} 監控中心</a>`
      + `<a href="${TEACHER}qrcode.html?group=${g}" target="_blank" rel="noopener">${esc(selected)} QR Code</a>`;
  }

  function renderView() {
    buildOptions();
    if (ROUNDS_ON) renderRounds();
    renderTeacherLinks();
    const top = lastRows[0];
    const d = lastData;
    if (!top) {
      $("groupInfo").textContent = "目前還沒有分析結果，請先按「開始模擬」";
      return;
    }
    const allG = selected === "ALL";
    const allB = selBatch === "ALL";
    const scope = [allG ? "" : selected, allB ? "" : batchLabel(selBatch)].filter(Boolean).join(" ");
    $("linesTitle").textContent = scope ? `${scope} 生產線分析` : "各組生產線分析";

    if (!d || !d.lines) {
      $("latest").textContent = top.message;
      $("groupInfo").textContent = "目前還沒有分析結果，請先按「開始模擬」";
      renderStations(null);
      return;
    }
    const lines = d.lines.filter((l) => (allG || l.group_id === selected) && matchBatch(l));
    const t = new Date(top.created_at || Date.now()).toLocaleTimeString("zh-TW", { hour12: false, timeZone: "Asia/Taipei" });
    const sum = (k) => lines.reduce((a, l) => a + (l[k] || 0), 0);
    // 排名：節拍時間越短越好；選了場次 → 跟同一場次的各組比
    const ranked = d.lines.filter(matchBatch).filter(rankable).sort((a, b) => a.takt_sec - b.takt_sec);
    const rankOf = (l) => (ranked.includes(l) ? `${ranked.indexOf(l) + 1}/${ranked.length}` : "不列入排名");
    const avgBal = lines.length ? (sum("balance_pct") / lines.length).toFixed(1) : "—";

    const u = new URL(location.href);
    $("groupInfo").textContent = scope ? `分享這個畫面：${u.origin}${u.pathname}${u.search}` : `共 ${d.groups} 組、${d.lines.length} 個場次有資料`;

    if (!lines.length) {
      $("latest").textContent = `${scope} 目前沒有資料（Python 第 ${top.tick ?? "—"} 次執行時）`;
      $("latestStats").innerHTML = "";
    } else if (allG && allB) {
      $("latest").textContent = top.message;
      const b = d.best;
      $("latestStats").innerHTML = tilesHtml([["事件筆數", d.events], ["組數", d.groups], ["場次數", d.lines.length],
        ["節拍時間最短", b ? `${b.group_id} ${batchLabel(b.batch)}（${b.takt_sec} 秒/組）` : "—"], ["平均平衡率", `${avgBal}%`]]);
    } else if (allG) {
      const best = ranked[0];
      $("latest").textContent = `[${t}] ${batchLabel(selBatch)}：共 ${lines.length} 組有資料`
        + (best ? `，節拍時間最短 ${best.group_id}（每組 ${best.takt_sec} 秒，瓶頸 ${best.bottleneck}）` : "") + `，平均平衡率 ${avgBal}%`;
      $("latestStats").innerHTML = tilesHtml([["事件筆數", sum("events")], ["組數", lines.length], ["完成組數", sum("output_sets")],
        ["節拍時間最短", best ? `${best.group_id}（${best.takt_sec} 秒/組）` : "—"], ["平均平衡率", `${avgBal}%`]]);
    } else {
      // 單一組別：逐場比較（改流程後有沒有變好）
      const cur = d.current_rounds?.[selected] || d.system_round;
      const parts = lines.map((l) => `${batchLabel(l.batch)} 節拍 ${l.takt_sec ?? "—"} 秒/組（完成 ${l.output_sets} 組、瓶頸 ${l.bottleneck}、排名 ${rankOf(l)}）`);
      $("latest").textContent = `[${t}] ${selected}：${parts.join("；")}`;
      const valid = lines.filter(rankable);
      const bestMine = valid.length ? valid.reduce((a, l) => (l.takt_sec < a.takt_sec ? l : a)) : null;
      const worst = lines.reduce((a, l) => (l.bottleneck_ct > a.bottleneck_ct ? l : a));
      $("latestStats").innerHTML = tilesHtml([["目前場次", cur ? roundLabel(cur) : "—"], ["有資料的場次", lines.length],
        ["最佳節拍時間", bestMine ? `${batchLabel(bestMine.batch)}（${bestMine.takt_sec} 秒/組）` : "—"],
        ["完成組數", sum("output_sets")], ["最慢工站", `${worst.bottleneck}（${worst.bottleneck_ct}s）`]]);
    }
    renderLines(lines, d.stations || [], `${scope} 目前沒有資料`);
    renderStations(!allG && !allB && selBatch !== "SELECTED" && lines.length === 1 ? lines[0] : null);
  }

  // ---------- 場次紀錄：讀取 / 顯示 / 儲存（直接寫 Supabase 的 round_selection 表） ----------
  const sbHeaders = () => ({ apikey: C.SUPABASE_KEY, "Content-Type": "application/json" });

  async function loadSelections() {
    if (!SB || !C.SUPABASE_KEY) { selState = "off"; renderRounds(); return; }
    try {
      const r = await fetch(`${SB}/rest/v1/round_selection?select=*&order=group_id.asc,round.asc`, { headers: sbHeaders() });
      if (r.status === 404) { selState = "missing"; renderRounds(); return; }
      if (!r.ok) throw new Error(`Supabase ${r.status}: ${await r.text()}`);
      const map = {};
      (await r.json()).forEach((row) => ((map[row.group_id] = map[row.group_id] || {})[row.round] = row));
      selMap = map;
      selState = "ok";
    } catch (e) {
      selState = "error"; selError = e.message;
    }
    renderRounds();
    if (selBatch === "SELECTED") renderView();
  }

  function lineFor(g, r) {
    return (lastData?.lines || []).find((l) => l.group_id === g && l.batch === r);
  }

  function renderRounds(force = false) {
    const hint = $("roundHint"), table = $("roundTable");
    const showForm = (on) => { $("btnSaveRounds").hidden = !on; $("btnResetRounds").hidden = !on; };
    if (selState === "off") {
      hint.textContent = "要先在 config.js 設定 SUPABASE_URL 和 SUPABASE_KEY，才能把場次存進資料庫。";
      table.innerHTML = ""; showForm(false); return;
    }
    if (selState === "missing") {
      hint.textContent = "資料庫還沒有 round_selection 資料表。請在 Supabase 後台 SQL Editor 執行 round_selection.sql（只需要一次）。";
      table.innerHTML = ""; showForm(false); return;
    }
    if (selState === "error") { hint.textContent = `讀取場次紀錄失敗：${selError}`; showForm(false); return; }
    if (selState === "init") { hint.textContent = "讀取場次紀錄中…"; showForm(false); return; }

    if (selected === "ALL") {
      // 全部組別：總覽表，不能編輯
      showForm(false);
      roundDirty = false; roundGroupShown = null;
      $("roundSub").textContent = "（全部組別總覽）";
      const groups = [...new Set([...Object.keys(selMap), ...(lastData?.lines || []).map((l) => l.group_id)])].sort();
      hint.textContent = groups.length ? "選擇上方的一個組別，就能勾選場次並儲存。" : "還沒有任何組別的場次紀錄。選擇上方的一個組別開始記錄。";
      const head = `<tr><th>組別</th>${ROUNDS.map((r) => `<th>${r === "FORMAL" ? "正式" : r.slice(4)}</th>`).join("")}</tr>`;
      const body = groups.map((g) => `<tr><td>${esc(g)}</td>${ROUNDS.map((r) => {
        const row = selMap[g]?.[r];
        if (row?.selected) return `<td class="c"><span class="tag ${row.result || "sel"}" title="${esc(roundLabel(r))}">${row.result ? esc(RESULT_LABEL[row.result]) : "已選"}</span></td>`;
        return `<td class="c">${lineFor(g, r) ? '<span class="muted" title="有資料、未選">·</span>' : ""}</td>`;
      }).join("")}</tr>`).join("");
      table.innerHTML = `<thead>${head}</thead><tbody>${body}</tbody>`;
      return;
    }

    // 單一組別：可編輯表單（正在修改時不重畫，避免打字到一半被洗掉）
    if (roundDirty && roundGroupShown === selected && !force) return;
    showForm(true);
    roundGroupShown = selected;
    roundDirty = false;
    $("roundMsg").textContent = "";
    const mine = selMap[selected] || {};
    const last = Object.values(mine).map((r) => r.updated_at).sort().pop();
    $("roundSub").textContent = `（${selected}）`;
    hint.textContent = `勾選 ${selected} 選擇的場次，標記是否通過，按「儲存到資料庫」。` + (last ? `上次儲存：${fmtTime(last)}` : "這一組還沒有儲存過。");
    const head = "<tr><th>場次</th><th>選擇</th><th>結果</th><th>備註</th><th>這場的資料</th></tr>";
    const body = ROUNDS.map((r) => {
      const row = mine[r] || {};
      const l = lineFor(selected, r);
      const info = l ? `${l.events} 筆・完成 ${l.finished} 件・${l.throughput_per_hr} 件/hr` : '<span class="muted">無資料</span>';
      return `<tr data-round="${r}" class="${row.selected ? "on" : ""}">
        <td>${esc(roundLabel(r))}</td>
        <td class="c"><input type="checkbox" id="sel-${r}" aria-label="選擇${esc(roundLabel(r))}" ${row.selected ? "checked" : ""}></td>
        <td><select id="res-${r}" aria-label="${esc(roundLabel(r))}結果">
          <option value="">未判定</option>
          <option value="pass" ${row.result === "pass" ? "selected" : ""}>通過</option>
          <option value="fail" ${row.result === "fail" ? "selected" : ""}>未通過</option></select></td>
        <td><input type="text" id="note-${r}" maxlength="200" placeholder="（選填）" value="${esc(row.note || "")}" aria-label="${esc(roundLabel(r))}備註"></td>
        <td>${info}</td></tr>`;
    }).join("");
    table.innerHTML = `<thead>${head}</thead><tbody>${body}</tbody>`;
  }

  // 任何修改 → 標記為未儲存；選了「通過／未通過」自動勾選
  $("roundTable").addEventListener("input", (ev) => {
    const tr = ev.target.closest("tr[data-round]");
    if (!tr) return;
    const r = tr.dataset.round;
    if (ev.target.id === `res-${r}` && ev.target.value) $(`sel-${r}`).checked = true;
    tr.classList.toggle("on", $(`sel-${r}`).checked);
    tr.classList.add("dirty");
    roundDirty = true;
    $("roundMsg").textContent = "有尚未儲存的修改";
  });

  $("btnResetRounds").onclick = () => { renderRounds(true); };

  $("btnSaveRounds").onclick = async () => {
    const g = roundGroupShown;
    if (!g) return;
    const mine = selMap[g] || {};
    const now = new Date().toISOString();
    // 只存「有勾、有結果、有備註，或原本就有紀錄」的場次
    const rows = ROUNDS.map((r) => ({
      group_id: g, round: r,
      selected: $(`sel-${r}`).checked,
      result: $(`res-${r}`).value || null,
      note: $(`note-${r}`).value.trim() || null,
      updated_at: now,
    })).filter((row) => row.selected || row.result || row.note || mine[row.round]);
    if (!rows.length) { $("roundMsg").textContent = "沒有要儲存的場次"; return; }
    $("btnSaveRounds").disabled = true;
    $("roundMsg").textContent = "儲存中…";
    try {
      const r = await fetch(`${SB}/rest/v1/round_selection?on_conflict=group_id,round`, {
        method: "POST",
        headers: { ...sbHeaders(), Prefer: "resolution=merge-duplicates,return=representation" },
        body: JSON.stringify(rows),
      });
      if (!r.ok) throw new Error(`Supabase ${r.status}: ${await r.text()}`);
      const saved = await r.json();
      saved.forEach((row) => ((selMap[row.group_id] = selMap[row.group_id] || {})[row.round] = row));
      roundDirty = false;
      renderRounds(true);
      const picked = saved.filter((x) => x.selected).map((x) => roundLabel(x.round));
      $("roundMsg").textContent = `已儲存 ${fmtTime(now)}：${picked.length ? picked.join("、") : "沒有選擇任何場次"}`;
      if (selBatch === "SELECTED") renderView();
    } catch (e) {
      $("roundMsg").textContent = `儲存失敗：${e.message}`;
    } finally {
      $("btnSaveRounds").disabled = false;
    }
  };

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

  buildOptions();
  $("roundCard").hidden = !ROUNDS_ON;
  if (ROUNDS_ON) {
    loadSelections();
    setInterval(() => { if (!roundDirty) loadSelections(); }, 30000);
  }
  refresh();
  setInterval(refresh, MODE === "static" ? 30000 : C.POLL_MS || 3000);
})();
