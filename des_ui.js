// 「經驗分布模擬」區塊：選好組別 + 場次 → 每站的經驗分布（已完成資料）→ 調參數 → 跑模擬（Python des.py 在瀏覽器裡執行）
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
  const LEVEL_ICON = { few: "🔴", low: "🟡", ok: "🟢", best: "⭐" };

  let key = "", model = null, loading = false, version = -1;

  function target() {
    const g = $("groupSel") ? $("groupSel").value : "ALL";
    const r = $("batchSel") ? $("batchSel").value : "ALL";
    return { g, r, src: $("desSource").value, ok: /^G\d+$/.test(g) && /^(TEST\d+|FORMAL)$/.test(r) };
  }

  // 小圖：這站的經驗分布（累積分布 CDF）。連續型 = 各點之間連直線；離散型 = 階梯
  function cdfSvg(vals, mode) {
    const n = vals.length;
    if (!n) return "";
    const W = 120, H = 30, lo = vals[0], hi = vals[n - 1], span = hi - lo || 1;
    const x = (v) => (n === 1 ? W / 2 : 4 + ((v - lo) / span) * (W - 8));
    let d;
    if (mode === "disc") {
      d = `M4 ${H - 3}` + vals.map((v, i) => ` H${x(v).toFixed(1)} V${(H - 3 - ((i + 1) / n) * (H - 6)).toFixed(1)}`).join("") + ` H${W - 4}`;
    } else {
      d = vals.map((v, i) => `${i ? "L" : "M"}${x(v).toFixed(1)} ${(H - 3 - (n === 1 ? 1 : i / (n - 1)) * (H - 6)).toFixed(1)}`).join(" ");
    }
    const dots = n <= 40 ? vals.map((v) => `<circle cx="${x(v).toFixed(1)}" cy="${H - 2}" r="1.6"/>`).join("") : "";
    return `<svg class="des-cdf" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="經驗分布 ${lo}～${hi} 秒">
      <path d="${d}" fill="none" stroke="currentColor" stroke-width="1.6"/><g fill="currentColor" opacity=".55">${dots}</g></svg>`;
  }

  function keepInputs() {   // 重新整理表格時，保留使用者改過的倍率、人數、站前在製品、站前上限
    const keep = {};
    card.querySelectorAll("input[data-f],input[data-k],input[data-i],input[data-c]").forEach((el) => {
      const [k, v] = Object.entries(el.dataset)[0];
      keep[k + ":" + v] = el.value;
    });
    return keep;
  }
  // 站前上限的預設值：依上方「站前上限」選單（資料庫設定／全部同一個數字／不限制）
  function capDefault(s) {
    const g = $("desWip").value;
    if (g === "none") return "";
    if (/^\d+$/.test(g)) return g;
    return s.wip_limit_in ?? "";
  }

  function renderParams(keep = {}) {
    const m = model, mode = $("desMode").value;
    $("desStations").innerHTML = `<thead><tr><th>工站</th><th>前站（齊套）</th><th>資料筆數（本場 + 加入）</th>
      <th>經驗分布（累積分布）</th><th>作業時間倍率</th><th>人數</th><th>站前在製品<br><small>開始時（件／套）</small></th><th>站前上限<br><small>空白 = 不限</small></th></tr></thead><tbody>` +
      m.stations.map((s) => {
        const o = s.own, a = s.added, p = s.pool;
        const addTxt = a.n ? ` + 加入 ${a.n}<br><small>${esc(s.used.slice(1).join("、"))}：平均 ${a.mean}（本場 ${o.mean ?? "—"}）</small>${s.diff_warn ? ` <span class="tag warn" title="加入的資料平均跟本場差 ${s.diff_pct}%，請確認做法相同再合併">差 ${s.diff_pct}%</span>` : ""}` : "";
        return `<tr${s.station === m.terminal ? ' class="des-term"' : ""}>
        <td><b>${esc(s.station)}</b>${s.station === m.terminal ? ' <span class="tag">終點</span>' : ""}${s.no_data ? ' <span class="tag warn">無資料</span>' : ""}</td>
        <td>${s.preds.length ? esc(s.preds.join(" + ")) : '<span class="muted">起點</span>'}</td>
        <td><b>${p.n}</b> <span class="des-lv des-lv-${s.level.code}">${LEVEL_ICON[s.level.code]} ${esc(s.level.label)}</span><br><small>本場 ${o.n}${addTxt}</small></td>
        <td>${cdfSvg(s.cdf, mode)}<br><small>${p.min ?? "—"}～${p.max ?? "—"} 秒｜平均 ${p.mean ?? "—"}｜中位數 ${p.median ?? "—"}</small></td>
        <td><input class="des-in" type="number" min="10" max="500" step="10" value="${keep["f:" + s.station] ?? 100}" data-f="${esc(s.station)}" aria-label="${esc(s.station)} 作業時間倍率"> %</td>
        <td><input class="des-in" type="number" min="1" max="5" step="1" value="${keep["k:" + s.station] ?? 1}" data-k="${esc(s.station)}" aria-label="${esc(s.station)} 人數"></td>
        ${s.preds.length ? `<td><input class="des-in" type="number" min="0" max="50" step="1" value="${keep["i:" + s.station] ?? s.init_wip_in ?? 0}" data-i="${esc(s.station)}" aria-label="${esc(s.station)} 開始時站前在製品"></td>
        <td><input class="des-in" type="number" min="1" max="50" step="1" value="${keep["c:" + s.station] ?? capDefault(s)}" data-c="${esc(s.station)}" placeholder="不限" aria-label="${esc(s.station)} 站前上限"></td>`
        : '<td colspan="2"><span class="muted">起點：原料無限，沒有站前在製品</span></td>'}</tr>`;
      }).join("") + "</tbody>";
    const minN = m.min_samples;
    const notes = [`資料來源：${m.source_label}（只用已完成的紀錄）`, `資料最少的工站 ${minN} 筆${minN < 30 ? "，未達實務起點 30 筆，結果僅供參考；可在「資料來源」加入之前的資料" : ""}`,
      `流程：${m.flow_source}`, `站前上限：${m.wip_limit_source}`, `開始時站前在製品：${m.init_wip_source}`];
    if (m.other_rounds.length) {
      notes.push("本組其他場次：" + m.other_rounds.map((r) => `${r.label}（${r.records} 筆）${r.same_flow ? "✓ " : "✗ 不加入："}${r.reason}`).join("；"));
    } else {
      notes.push("本組沒有其他場次的資料");
    }
    if (m.missing_data.length) notes.push(`${m.missing_data.join("、")} 沒有任何資料，暫用全部資料的中位數`);
    if (m.ignored_stations.length) notes.push(`${m.ignored_stations.join("、")} 有紀錄但不在流程裡，模擬不使用`);
    $("desModelNote").textContent = notes.join("｜");
  }

  async function loadModel(force = false) {
    const t = target();
    const k = `${t.g}|${t.r}|${t.src}`;
    if (!force && k === key) return;
    const sameLine = key.split("|").slice(0, 2).join("|") === `${t.g}|${t.r}`;
    const keep = sameLine ? keepInputs() : {};
    key = k;
    if (!sameLine) $("desResult").hidden = true;
    if (!t.ok) {
      model = null;
      $("desTarget").textContent = "請先在上方「選擇組別」選一組、「選擇場次」選一個場次（例如 G23、第 1 次測試），就會用那一場已完成的加工時間建立經驗分布。";
      $("desStations").innerHTML = ""; $("desModelNote").textContent = "";
      $("desRun").disabled = true;
      return;
    }
    if (!model || !sameLine) $("desTarget").textContent = `模型：${t.g} ${roundLabel(t.r)}（讀取中…）`;
    loading = true;
    try {
      const m = await BrowserEngine.desModel(t.g, t.r, t.src);
      if (`${t.g}|${t.r}|${t.src}` !== key) return;   // 讀取途中又換了選擇
      if (!m.ok) { model = null; $("desTarget").textContent = m.error; $("desStations").innerHTML = ""; $("desModelNote").textContent = ""; $("desRun").disabled = true; return; }
      const firstLoad = !model || !sameLine;
      model = m;
      const a = m.actual;
      $("desTarget").innerHTML = `模型：<b>${esc(t.g)} ${roundLabel(t.r)}</b>　本場已完成：${a.output_sets} 組、總耗時 ${fmtSec(a.total_sec)}、產線 Cycle Time ${a.takt_sec ?? "—"} 秒/組、瓶頸 ${esc(a.bottleneck)}`;
      if (firstLoad) $("desN").value = a.output_sets || 10;
      renderParams(keep);
      $("desRun").disabled = false;
    } catch (e) {
      $("desTarget").textContent = `建立模型失敗：${e.message}`;
    } finally { loading = false; }
  }

  function params() {
    const factor = {}, servers = {};
    card.querySelectorAll("input[data-f]").forEach((el) => { const v = Number(el.value); if (v > 0 && v !== 100) factor[el.dataset.f] = v / 100; });
    card.querySelectorAll("input[data-k]").forEach((el) => { const v = Math.round(Number(el.value)); if (v > 1) servers[el.dataset.k] = v; });
    const wip = {}, init = {};   // 每一站分別設定：站前上限（空白 = 不限）、開始時站前在製品
    card.querySelectorAll("input[data-c]").forEach((el) => { const v = Math.round(Number(el.value)); wip[el.dataset.c] = el.value.trim() !== "" && v > 0 ? v : null; });
    card.querySelectorAll("input[data-i]").forEach((el) => { init[el.dataset.i] = Math.max(0, Math.round(Number(el.value) || 0)); });
    return { n_sets: Math.max(1, Math.round(Number($("desN").value) || 10)), reps: Math.max(10, Math.min(2000, Math.round(Number($("desR").value) || 200))),
      seed: Math.round(Number($("desSeed").value) || 2026), mode: $("desMode").value, wip, init, factor, servers };
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
      ["理論最快 Cycle Time", `${r.bound_ct_sec} 秒/組<br><small>受限於 ${esc(r.bound_station)}（平均加工時間 ÷ 人數）</small>`],
      ...(sameN ? [["實際（同樣做 " + a.output_sets + " 組）", `${fmtSec(a.total_sec)}<br><small>產線 Cycle Time ${a.takt_sec} 秒/組</small>`]] : []),
    ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");

    $("desStTable").innerHTML = `<thead><tr><th>工站</th><th>資料筆數</th><th>有效加工時間</th><th>利用率（在加工）</th><th>阻塞（做完送不出去）</th><th>閒置（等料）</th><th>當瓶頸的比例</th></tr></thead><tbody>` +
      r.stations.map((s) => `<tr${s.station === r.bottleneck ? ' class="des-bn"' : ""}><td>${esc(s.station)}${s.factor !== 1 ? ` <span class="tag">×${Math.round(s.factor * 100)}%</span>` : ""}${s.servers > 1 ? ` <span class="tag">${s.servers} 人</span>` : ""}</td>
        <td>${r.samples[s.station] ?? "—"}</td><td>${s.eff_time} 秒</td><td>${bar(s.util_pct, "var(--accent)")}</td><td>${bar(s.blocked_pct, "#a855f7")}</td><td>${bar(s.starved_pct, "#eab308")}</td><td>${s.bottleneck_share_pct}%</td></tr>`).join("") + "</tbody>";
    // 各站站前在製品（起點站原料無限，不列）
    const ws = r.stations.filter((s) => s.wip_avg !== undefined);
    $("desWipTable").innerHTML = `<thead><tr><th>工站</th><th>開始時</th><th>上限</th><th>平均在製品（時間加權）</th><th>最多同時</th><th>結束時還剩</th><th>每件平均在站前等待</th></tr></thead><tbody>` +
      ws.map((s) => `<tr${s.station === r.bottleneck ? ' class="des-bn"' : ""}><td>${esc(s.station)} 前</td><td>${s.init_wip}</td><td>${s.wip_limit ?? "不限"}</td>
        <td>${s.wip_avg} 件</td><td>${s.wip_max} 件</td><td>${s.wip_end} 件</td><td>${s.wait_avg == null ? "—" : fmtSec(s.wait_avg)}</td></tr>`).join("") + "</tbody>";
    $("desWipChart").innerHTML = wipCharts(r.wip_timeline, r.bottleneck);
    $("desBufTable").innerHTML = `<thead><tr><th>站間緩衝區</th><th>上限</th><th>平均 WIP（時間加權）</th><th>最多同時</th></tr></thead><tbody>` +
      r.buffers.map((b) => `<tr><td>${esc(b.buffer)}</td><td>${b.limit ?? "不限制"}</td><td>${b.avg_wip}</td><td>${b.max_wip}</td></tr>`).join("") + "</tbody>";

    const modeTxt = { cont: "連續型經驗分布（分段線性）", disc: "離散型經驗分布（重抽樣）", mean: "固定用平均值（沒有波動）" }[p.mode];
    const notes = [`加工時間：${modeTxt}｜資料來源：${r.data_source}，最少的工站 ${r.min_samples} 筆${r.min_samples < 30 ? "（未達 30 筆，僅供參考）" : ""}`,
      `重複 ${r.completed_reps} 次（亂數種子 ${p.seed}，同樣設定再跑一次結果會一樣）`];
    if (sameN) {
      const gap = (a.total_sec - r.makespan_sec.mean) / a.total_sec * 100;
      notes.push(gap > 0
        ? `實際比模擬多花 ${gap.toFixed(0)}% 的時間：模擬只算「加工 + 排隊等料 + 阻塞」，實際還有傳遞、溝通、走動、掃碼等時間`
        : `實際比模擬快 ${(-gap).toFixed(0)}%`);
    }
    $("desNote").textContent = notes.join("｜");
    // 圖 B：每一次模擬的結果
    $("desRepChart").innerHTML = repChart(r.reps_detail);
    $("desRepNote").textContent = repNote(r.reps_detail);
    $("desResult").hidden = false;
  }

  // 各站前在製品隨時間的變化（第 1 次模擬）：每一站一張小階梯圖，縱軸刻度相同方便比較
  function wipCharts(tl, bott) {
    const sts = Object.keys(tl || {}).sort();
    if (!sts.length) return "";
    const end = Math.max(...sts.map((s) => tl[s][tl[s].length - 1][0]), 1);
    const top = Math.max(1, ...sts.flatMap((s) => tl[s].map((p) => p[1])));
    const W = 260, H = 70, L = 22, B = 14;
    const x = (t) => L + (t / end) * (W - L - 4), y = (v) => 4 + (1 - v / top) * (H - B - 4);
    return sts.map((s) => {
      const pts = tl[s];
      let d = `M${x(0).toFixed(1)} ${y(pts[0][1]).toFixed(1)}`;
      for (let i = 1; i < pts.length; i++) d += ` H${x(pts[i][0]).toFixed(1)} V${y(pts[i][1]).toFixed(1)}`;
      const mx = Math.max(...pts.map((p) => p[1]));
      return `<figure class="des-wipfig${s === bott ? " bn" : ""}"><figcaption>${esc(s)} 前${s === bott ? "（瓶頸）" : ""}<span>最多 ${mx} 件</span></figcaption>
        <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(s)} 前在製品隨時間變化，最多 ${mx} 件">
          <line x1="${L}" y1="${y(0)}" x2="${W - 4}" y2="${y(0)}" class="ax"/><text x="${L - 4}" y="${y(top) + 4}" class="lb" text-anchor="end">${top}</text>
          <text x="${L - 4}" y="${y(0) + 4}" class="lb" text-anchor="end">0</text><text x="${W - 4}" y="${H - 1}" class="lb" text-anchor="end">${fmtSec(end)}</text>
          <path d="${d}" fill="none" stroke="currentColor" stroke-width="1.8"/></svg></figure>`;
    }).join("");
  }

  // ---------------- 圖 B：每一次模擬的結果（灰點 = 每一次的產線 CT；藍線 = 累積平均）
  function repChart(det) {
    if (!det || !det.length) return "";
    const ys = det.map((d) => d.ct), R = ys.length;
    const cum = []; let acc = 0;
    ys.forEach((y, i) => { acc += y; cum.push(acc / (i + 1)); });
    const fin = cum[R - 1];
    let lo = Math.min(...ys), hi = Math.max(...ys);
    const pad = (hi - lo || 1) * 0.08; lo -= pad; hi += pad;
    const W = 640, H = 240, L = 46, Rm = 14, T = 12, B = 34;
    const x = (i) => L + (R === 1 ? 0.5 : i / (R - 1)) * (W - L - Rm);
    const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const ticks = [0, 1, 2, 3, 4].map((k) => lo + (hi - lo) * k / 4);
    const xt = [...new Set([0, Math.round((R - 1) / 4), Math.round((R - 1) / 2), Math.round(3 * (R - 1) / 4), R - 1])];
    const dots = R <= 600
      ? ys.map((v, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${R > 200 ? 1.6 : 2.2}" class="dot"/>`).join("")
      : `<polyline points="${ys.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}" class="raw"/>`;
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${R} 次模擬的產線 Cycle Time 與累積平均，最後平均 ${fin.toFixed(1)} 秒/組">
      <rect x="${L}" y="${y(fin * 1.01).toFixed(1)}" width="${W - L - Rm}" height="${Math.max(1, y(fin * 0.99) - y(fin * 1.01)).toFixed(1)}" class="band"/>
      ${ticks.map((v) => `<line x1="${L}" x2="${W - Rm}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="grid"/><text x="${L - 6}" y="${(y(v) + 4).toFixed(1)}" class="lb" text-anchor="end">${v.toFixed(1)}</text>`).join("")}
      ${xt.map((i) => `<text x="${x(i).toFixed(1)}" y="${H - 16}" class="lb" text-anchor="middle">${i + 1}</text>`).join("")}
      <text x="${(L + W - Rm) / 2}" y="${H - 2}" class="lb" text-anchor="middle">第幾次模擬</text>
      <text x="12" y="${(T + H - B) / 2}" class="lb" text-anchor="middle" transform="rotate(-90 12 ${(T + H - B) / 2})">產線 CT（秒/組）</text>
      ${dots}
      <line x1="${L}" x2="${W - Rm}" y1="${y(fin).toFixed(1)}" y2="${y(fin).toFixed(1)}" class="fin"/>
      <polyline points="${cum.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}" class="cum"/>
    </svg>
    <div class="des-legend"><span><i class="dot"></i>每一次的產線 CT</span><span><i class="cum"></i>累積平均（前 k 次的平均）</span><span><i class="band"></i>最後平均 ±1%</span></div>`;
  }
  // 累積平均從第幾次之後一直落在最後平均的 ±1% 以內 → 大概要跑幾次才夠
  function repNote(det) {
    if (!det || det.length < 2) return "";
    const ys = det.map((d) => d.ct), R = ys.length;
    const cum = []; let acc = 0;
    ys.forEach((y, i) => { acc += y; cum.push(acc / (i + 1)); });
    const fin = cum[R - 1];
    let k = R;
    for (let i = R - 1; i >= 0 && Math.abs(cum[i] - fin) <= fin * 0.01; i--) k = i + 1;
    const first10 = cum[Math.min(9, R - 1)];
    return `共 ${R} 次：每一次的產線 CT 介於 ${Math.min(...ys).toFixed(1)}～${Math.max(...ys).toFixed(1)} 秒/組（每次抽到的加工時間不同）。` +
      `前 ${Math.min(10, R)} 次的平均是 ${first10.toFixed(1)}，全部 ${R} 次是 ${fin.toFixed(1)}；` +
      (k < R ? `從第 ${k} 次之後，累積平均就一直在 ±1% 以內，代表跑 ${k} 次左右結果就穩定了。` : `累積平均還沒穩定在 ±1% 以內，建議增加模擬次數。`);
  }

  // ---------------- 模擬紀錄：每按一次「跑模擬」存一筆（存在這台電腦的瀏覽器裡）
  const REC_KEY = "des-records-v1", REC_MAX = 50;
  let records = [];
  try { records = JSON.parse(localStorage.getItem(REC_KEY) || "[]"); } catch { records = []; }
  const checked = new Set(records.slice(-5).map((r) => r.id));
  function persist() {
    try { localStorage.setItem(REC_KEY, JSON.stringify(records)); }
    catch {   // 瀏覽器空間不夠：舊紀錄只留摘要，不留每一次的結果
      records.forEach((r, i) => { if (i < records.length - 5) delete r.cts; });
      try { localStorage.setItem(REC_KEY, JSON.stringify(records)); } catch {}
    }
  }
  // 這一次跟預設不一樣的設定（倍率、人數、站前在製品、站前上限）
  function settingsText(p) {
    const out = [];
    Object.entries(p.factor || {}).forEach(([st, f]) => out.push(`${st} 時間×${Math.round(f * 100)}%`));
    Object.entries(p.servers || {}).forEach(([st, k]) => out.push(`${st} ${k} 人`));
    model.stations.forEach((s) => {
      if (!s.preds.length) return;
      const i = p.init?.[s.station] ?? 0, c = p.wip?.[s.station];
      if (i !== (s.init_wip_in ?? 0)) out.push(`${s.station} 前開始 ${i} 件`);
      if ((c ?? null) !== (s.wip_limit_in ?? null)) out.push(`${s.station} 前上限 ${c ?? "不限"}`);
    });
    return out.length ? out.join("、") : "現況（預設設定）";
  }
  function saveRecord(r, t) {
    const p = params();
    const modeTxt = { cont: "連續型", disc: "離散型", mean: "固定平均" }[r.params.mode];
    const rec = {
      id: (records.length ? records[records.length - 1].id : 0) + 1, at: new Date().toISOString(),
      line: `${t.g} ${roundLabel(t.r)}`, source: model.source_label, dist: modeTxt, minSamples: r.min_samples,
      n: r.params.n_sets, reps: r.completed_reps, seed: r.params.seed, settings: settingsText(p),
      makespan: r.makespan_sec, ct: r.line_ct_sec, tp: r.throughput_per_hr, bott: r.bottleneck, bshare: r.bottleneck_share_pct,
      actual: { n: model.actual.output_sets, total: model.actual.total_sec, ct: model.actual.takt_sec },
      cts: r.reps_detail.map((d) => d.ct), seeds: [r.reps_detail[0]?.seed ?? r.params.seed],
    };
    records.push(rec);
    while (records.length > REC_MAX) records.shift();
    checked.add(rec.id);
    persist();
    renderRecords();
  }
  const fmtAt = (iso) => new Date(iso).toLocaleString("zh-TW", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  function renderRecords() {
    $("desHistBox").hidden = !records.length;
    if (!records.length) return;
    $("desHistTable").innerHTML = `<thead><tr><th></th><th>#</th><th>時間</th><th>組別場次</th><th>設定</th><th>資料、分布</th><th>做幾組</th><th>模擬次數</th>
      <th>完成時間（90% 範圍）</th><th>產線 CT（90% 範圍）</th><th>每小時</th><th>瓶頸</th></tr></thead><tbody>` +
      records.slice().reverse().map((r) => `<tr><td><input type="checkbox" data-rec="${r.id}" ${checked.has(r.id) ? "checked" : ""} aria-label="比較紀錄 ${r.id}"></td>
        <td>${r.id}</td><td>${fmtAt(r.at)}</td><td>${esc(r.line)}</td><td class="des-set">${esc(r.settings)}</td>
        <td><small>${esc(r.source)}，最少 ${r.minSamples} 筆；${esc(r.dist)}</small></td><td>${r.n}</td><td>${r.reps}</td>
        <td>${fmtSec(r.makespan.mean)}<br><small>${fmtSec(r.makespan.p5)}～${fmtSec(r.makespan.p95)}</small></td>
        <td><b>${r.ct.mean}</b> 秒/組<br><small>${r.ct.p5}～${r.ct.p95}</small></td><td>${r.tp} 組</td><td>${esc(r.bott)}<br><small>${r.bshare}%</small></td></tr>`).join("") + "</tbody>";
    $("desCmpChart").innerHTML = cmpChart(records.filter((r) => checked.has(r.id)));
  }
  // 比較勾選的紀錄：點 = 產線 CT 平均，橫線 = 90% 範圍；同一個橫軸
  function cmpChart(rs) {
    if (!rs.length) return '<p class="hint">勾選上表的紀錄，就會畫在這裡比較。</p>';
    const lo0 = Math.min(...rs.map((r) => r.ct.p5)), hi0 = Math.max(...rs.map((r) => r.ct.p95));
    const pad = (hi0 - lo0 || 1) * 0.1, lo = Math.max(0, lo0 - pad), hi = hi0 + pad;
    const W = 640, row = 30, L = 210, Rm = 16, T = 8, H = T + rs.length * row + 30;
    const x = (v) => L + (v - lo) / (hi - lo) * (W - L - Rm);
    const ticks = [0, 1, 2, 3, 4].map((k) => lo + (hi - lo) * k / 4);
    const lab = (r) => { const s = `#${r.id} ${r.line}｜${r.settings}`; return s.length > 26 ? s.slice(0, 25) + "…" : s; };
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="比較 ${rs.length} 筆模擬紀錄的產線 Cycle Time">
      ${ticks.map((v) => `<line x1="${x(v).toFixed(1)}" x2="${x(v).toFixed(1)}" y1="${T}" y2="${H - 26}" class="grid"/><text x="${x(v).toFixed(1)}" y="${H - 12}" class="lb" text-anchor="middle">${v.toFixed(1)}</text>`).join("")}
      <text x="${(L + W - Rm) / 2}" y="${H - 1}" class="lb" text-anchor="middle">產線 Cycle Time（秒/組）</text>
      ${rs.map((r, i) => { const cy = T + i * row + row / 2; return `<text x="${L - 8}" y="${cy + 4}" class="lb2" text-anchor="end"><title>#${r.id} ${esc(r.line)}｜${esc(r.settings)}</title>${esc(lab(r))}</text>
        <line x1="${x(r.ct.p5).toFixed(1)}" x2="${x(r.ct.p95).toFixed(1)}" y1="${cy}" y2="${cy}" class="rng"/>
        <circle cx="${x(r.ct.mean).toFixed(1)}" cy="${cy}" r="5" class="mean"/><text x="${(x(r.ct.mean) + 8).toFixed(1)}" y="${cy - 7}" class="lb">${r.ct.mean}</text>`; }).join("")}
    </svg>`;
  }
  function csvDownload(name, rows) {
    const text = "﻿" + rows.map((r) => r.map((c) => { const v = String(c ?? ""); return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v; }).join(",")).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  $("desHistTable").addEventListener("change", (e) => {
    const id = Number(e.target.dataset.rec);
    if (!id) return;
    e.target.checked ? checked.add(id) : checked.delete(id);
    $("desCmpChart").innerHTML = cmpChart(records.filter((r) => checked.has(r.id)));
  });
  $("desHistCsv").onclick = () => csvDownload("模擬紀錄.csv", [["#", "時間", "組別場次", "設定", "資料來源", "經驗分布", "資料最少的工站筆數", "做幾組", "模擬次數", "亂數種子",
    "完成時間平均(秒)", "完成時間5%", "完成時間95%", "產線CT平均(秒/組)", "產線CT 5%", "產線CT 95%", "每小時產出(組)", "瓶頸", "瓶頸比例(%)", "實際組數", "實際總耗時(秒)", "實際產線CT"],
    ...records.map((r) => [r.id, fmtAt(r.at), r.line, r.settings, r.source, r.dist, r.minSamples, r.n, r.reps, r.seed,
      r.makespan.mean, r.makespan.p5, r.makespan.p95, r.ct.mean, r.ct.p5, r.ct.p95, r.tp, r.bott, r.bshare, r.actual.n, r.actual.total, r.actual.ct])]);
  $("desHistRepCsv").onclick = () => {
    const rs = records.filter((r) => checked.has(r.id) && r.cts);
    if (!rs.length) { alert("請先勾選要下載的紀錄"); return; }
    csvDownload("每一次模擬的結果.csv", [["紀錄#", "組別場次", "設定", "第幾次模擬", "亂數種子", "產線CT(秒/組)"],
      ...rs.flatMap((r) => r.cts.map((ct, i) => [r.id, r.line, r.settings, i + 1, r.seed + i, ct]))]);
  };
  $("desHistDel").onclick = () => {
    if (!checked.size) return;
    if (!confirm(`刪除勾選的 ${checked.size} 筆紀錄？`)) return;
    records = records.filter((r) => !checked.has(r.id)); checked.clear(); persist(); renderRecords();
  };
  $("desHistClear").onclick = () => {
    if (!confirm("清除全部模擬紀錄？（只會清這台電腦瀏覽器裡的紀錄）")) return;
    records = []; checked.clear(); persist(); renderRecords();
  };
  renderRecords();

  async function run() {
    if (!model) return;
    const t = target();
    $("desRun").disabled = true;
    $("desMsg").textContent = "模擬中…（第一次要先下載 Python）";
    const t0 = performance.now();
    try {
      const r = await BrowserEngine.simulate(t.g, t.r, t.src, params());
      if (!r.ok) { $("desMsg").textContent = r.error; return; }
      renderResult(r);
      saveRecord(r, t);
      $("desMsg").textContent = `完成：${r.completed_reps} 次模擬，用了 ${((performance.now() - t0) / 1000).toFixed(1)} 秒`;
    } catch (e) {
      $("desMsg").textContent = `模擬失敗：${e.message}`;
    } finally { $("desRun").disabled = false; }
  }

  $("desRun").onclick = run;
  $("desSource").onchange = () => loadModel(true);
  $("desMode").onchange = () => { if (model) renderParams(keepInputs()); };
  // 上方「站前上限」選單：一次把每一站的上限設成同一個（之後還可以個別修改）
  $("desWip").onchange = () => {
    if (!model) return;
    card.querySelectorAll("input[data-c]").forEach((el) => { el.value = capDefault(model.stations.find((s) => s.station === el.dataset.c) || {}); });
  };
  $("desReset").onclick = () => {
    $("desR").value = 200; $("desSeed").value = 2026; $("desMode").value = "cont"; $("desWip").value = "db"; $("desSource").value = "round";
    $("desMsg").textContent = "";
    key = ""; model = null;
    loadModel(true);
  };
  // 上方的組別、場次一改就重建模型（app.js 也可能用網址參數設定選擇，所以定時檢查）
  setInterval(() => { if (!loading) loadModel(); }, 800);
  // 即時：每 5 秒讀一次資料庫，有新完成的紀錄就更新各站經驗分布（保留改過的倍率、人數）
  setInterval(async () => {
    if (loading || !target().ok) return;
    try {
      const v = await BrowserEngine.desRefresh();
      if (version !== -1 && v !== version) await loadModel(true);
      version = v;
    } catch {}
  }, 5000);
})();
