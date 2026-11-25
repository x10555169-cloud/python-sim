// 「離散事件模擬」區塊：選好組別 + 場次 → 看模型 → 調參數 → 跑模擬（Python des.py 在瀏覽器裡執行）
(() => {
  const C = window.APP_CONFIG || {};
  const $ = (id) => document.getElementById(id);
  const card = $("desCard");
  if (!card || C.MODE !== "browser" || !window.BrowserEngine) return;   // 只有不用 Render 的瀏覽器模式才有
  card.hidden = false;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtSec = (s) => (s == null ? "—" : s < 60 ? `${s.toFixed(1)} 秒` : `${Math.floor(s / 60)} 分 ${String(Math.round(s % 60)).padStart(2, "0")} 秒`);
  const roundLabel = (r) => (r === "FORMAL" ? "正式實作" : `第 ${String(r).slice(4)} 次測試`);
  const bar = (pct, color) => `<span class="des-bar"><i style="width:${Math.min(100, Math.max(0, pct))}%;background:${color}"></i></span>${pct.toFixed(1)}%`;

  let key = "", model = null, loading = false;

  function target() {
    const g = $("groupSel") ? $("groupSel").value : "ALL";
    const r = $("batchSel") ? $("batchSel").value : "ALL";
    return { g, r, ok: /^G\d+$/.test(g) && /^(TEST\d+|FORMAL)$/.test(r) };
  }

  function renderParams() {
    const m = model;
    $("desStations").innerHTML = `<thead><tr><th>工站</th><th>前站（齊套）</th><th>實際件數</th><th>實際平均 CT</th><th>最快～最慢</th>
      <th>作業時間倍率</th><th>人數</th><th>送進本站的 WIP 上限</th></tr></thead><tbody>` +
      m.stations.map((s) => `<tr${s.station === m.terminal ? ' class="des-term"' : ""}>
        <td>${esc(s.station)}${s.station === m.terminal ? ' <span class="tag">終點</span>' : ""}${s.no_data ? ' <span class="tag warn">無資料</span>' : ""}</td>
        <td>${s.preds.length ? esc(s.preds.join(" + ")) : '<span class="muted">起點（原料無限）</span>'}</td>
        <td>${s.count}</td><td>${s.mean == null ? "—" : s.mean + " 秒"}</td>
        <td>${s.min == null ? "—" : `${s.min}～${s.max} 秒`}</td>
        <td><input class="des-in" type="number" min="10" max="500" step="10" value="100" data-f="${esc(s.station)}" aria-label="${esc(s.station)} 作業時間倍率"> %</td>
        <td><input class="des-in" type="number" min="1" max="5" step="1" value="1" data-k="${esc(s.station)}" aria-label="${esc(s.station)} 人數"></td>
        <td>${s.wip_limit_in == null ? '<span class="muted">—</span>' : s.wip_limit_in}</td></tr>`).join("") + "</tbody>";
    const notes = [`流程：${m.flow_source}`, `WIP 上限：${m.wip_limit_source}`];
    if (m.missing_data.length) notes.push(`${m.missing_data.join("、")} 還沒有紀錄，暫用全線作業時間的中位數`);
    if (m.ignored_stations.length) notes.push(`${m.ignored_stations.join("、")} 有紀錄但不在流程裡，模擬不使用`);
    $("desModelNote").textContent = notes.join("｜");
  }

  async function loadModel(force = false) {
    const t = target();
    const k = `${t.g}|${t.r}`;
    if (!force && k === key) return;
    key = k;
    $("desResult").hidden = true;
    if (!t.ok) {
      model = null;
      $("desTarget").textContent = "請先在上方「選擇組別」選一組、「選擇場次」選一個場次（例如 G23、第 1 次測試），就會用那一場的實際作業時間建立模型。";
      $("desStations").innerHTML = ""; $("desModelNote").textContent = "";
      $("desRun").disabled = true;
      return;
    }
    $("desTarget").textContent = `模型：${t.g} ${roundLabel(t.r)}（讀取中…）`;
    $("desRun").disabled = true;
    loading = true;
    try {
      const m = await BrowserEngine.desModel(t.g, t.r);
      if (`${t.g}|${t.r}` !== key) return;   // 讀取途中又換了選擇
      if (!m.ok) { model = null; $("desTarget").textContent = m.error; $("desStations").innerHTML = ""; $("desModelNote").textContent = ""; return; }
      model = m;
      const a = m.actual;
      $("desTarget").innerHTML = `模型：<b>${esc(t.g)} ${roundLabel(t.r)}</b>　實際：完成 ${a.output_sets} 組、總耗時 ${fmtSec(a.total_sec)}、產線 Cycle Time ${a.takt_sec ?? "—"} 秒/組、瓶頸 ${esc(a.bottleneck)}`;
      $("desN").value = a.output_sets || 10;
      renderParams();
      $("desRun").disabled = false;
    } catch (e) {
      $("desTarget").textContent = `建立模型失敗：${e.message}`;
    } finally { loading = false; }
  }

  function params() {
    const factor = {}, servers = {};
    card.querySelectorAll("input[data-f]").forEach((el) => { const v = Number(el.value); if (v > 0 && v !== 100) factor[el.dataset.f] = v / 100; });
    card.querySelectorAll("input[data-k]").forEach((el) => { const v = Math.round(Number(el.value)); if (v > 1) servers[el.dataset.k] = v; });
    const wip = $("desWip").value;
    return { n_sets: Math.max(1, Math.round(Number($("desN").value) || 10)), reps: Math.max(10, Math.min(2000, Math.round(Number($("desR").value) || 200))),
      seed: Math.round(Number($("desSeed").value) || 2026), mode: $("desMode").value,
      wip: /^\d+$/.test(wip) ? Number(wip) : wip, factor, servers };
  }

  function renderResult(r) {
    const a = model.actual, p = r.params;
    const range = (x, sec = false) => `<small>90% 落在 ${sec ? x.p5 : fmtSec(x.p5)}～${sec ? x.p95 + " 秒" : fmtSec(x.p95)}</small>`;
    const sameN = p.n_sets === a.output_sets && a.total_sec > 0;
    $("desStats").innerHTML = [
      [`完成 ${p.n_sets} 組要多久（預測）`, `${fmtSec(r.makespan_sec.mean)}<br>${range(r.makespan_sec)}`],
      ["產線 Cycle Time（預測）", `${r.line_ct_sec.mean} 秒/組<br>${range(r.line_ct_sec, true)}`],
      ["每小時產出（預測）", `${r.throughput_per_hr} 組`],
      ["瓶頸站（利用率最高）", `${esc(r.bottleneck)}<br><small>${r.bottleneck_share_pct}% 的模擬中是它</small>`],
      ["理論最快 Cycle Time", `${r.bound_ct_sec} 秒/組<br><small>受限於 ${esc(r.bound_station)}（平均作業時間 ÷ 人數）</small>`],
      ...(sameN ? [["實際（同樣做 " + a.output_sets + " 組）", `${fmtSec(a.total_sec)}<br><small>產線 Cycle Time ${a.takt_sec} 秒/組</small>`]] : []),
    ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");

    $("desStTable").innerHTML = `<thead><tr><th>工站</th><th>有效作業時間</th><th>利用率（在加工）</th><th>阻塞（做完送不出去）</th><th>閒置（等料）</th><th>當瓶頸的比例</th></tr></thead><tbody>` +
      r.stations.map((s) => `<tr${s.station === r.bottleneck ? ' class="des-bn"' : ""}><td>${esc(s.station)}${s.factor !== 1 ? ` <span class="tag">×${Math.round(s.factor * 100)}%</span>` : ""}${s.servers > 1 ? ` <span class="tag">${s.servers} 人</span>` : ""}</td>
        <td>${s.eff_time} 秒</td><td>${bar(s.util_pct, "var(--accent)")}</td><td>${bar(s.blocked_pct, "#a855f7")}</td><td>${bar(s.starved_pct, "#eab308")}</td><td>${s.bottleneck_share_pct}%</td></tr>`).join("") + "</tbody>";
    $("desBufTable").innerHTML = `<thead><tr><th>站間緩衝區</th><th>上限</th><th>平均 WIP（時間加權）</th><th>最多同時</th></tr></thead><tbody>` +
      r.buffers.map((b) => `<tr><td>${esc(b.buffer)}</td><td>${b.limit ?? "不限制"}</td><td>${b.avg_wip}</td><td>${b.max_wip}</td></tr>`).join("") + "</tbody>";

    const notes = [`重複 ${r.completed_reps} 次（亂數種子 ${p.seed}，同樣設定再跑一次結果會一樣）`,
      p.mode === "mean" ? "作業時間固定用平均值" : "每件作業時間從實際紀錄隨機抽一筆"];
    if (sameN) {
      const gap = (a.total_sec - r.makespan_sec.mean) / a.total_sec * 100;
      notes.push(gap > 0
        ? `實際比模擬多花 ${gap.toFixed(0)}% 的時間：模擬只算「加工 + 排隊等料 + 阻塞」，實際還有傳遞、溝通、走動、掃碼等時間`
        : `實際比模擬快 ${(-gap).toFixed(0)}%`);
    }
    $("desNote").textContent = notes.join("｜");
    $("desResult").hidden = false;
  }

  async function run() {
    if (!model) return;
    const t = target();
    $("desRun").disabled = true;
    $("desMsg").textContent = "模擬中…（第一次要先下載 Python）";
    const t0 = performance.now();
    try {
      const r = await BrowserEngine.simulate(t.g, t.r, params());
      if (!r.ok) { $("desMsg").textContent = r.error; return; }
      renderResult(r);
      $("desMsg").textContent = `完成：${r.completed_reps} 次模擬，用了 ${((performance.now() - t0) / 1000).toFixed(1)} 秒`;
    } catch (e) {
      $("desMsg").textContent = `模擬失敗：${e.message}`;
    } finally { $("desRun").disabled = false; }
  }

  $("desRun").onclick = run;
  $("desReset").onclick = () => {
    $("desR").value = 200; $("desSeed").value = 2026; $("desMode").value = "sample"; $("desWip").value = "db";
    $("desMsg").textContent = "";
    loadModel(true);
  };
  // 上方的組別、場次一改就重建模型（app.js 也可能用網址參數設定選擇，所以定時檢查）
  setInterval(() => { if (!loading) loadModel(); }, 800);
})();
