// 老師「即時監控中心」(工蓋螢幕.html) 的統計算法，逐行照抄成可獨立執行的版本，用來跟 Python 比對。
// 來源函式：getTestRoundFromProductId、isEventInViewRound、fetchAndResolveFlowsForRound（候選流程順序）、showStats。
// 用法：node verify_teacher.js events.json flows.json  → 輸出每個「組別|場次」的結果 JSON
const fs = require("fs");
const events = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const flows = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

// getTestRoundFromProductId / isTestProductId
function isTestProductId(pid) { return (pid || "").trim().toUpperCase().startsWith("TEST"); }
function getTestRoundFromProductId(pid) {
  const s = (pid || "").trim().toUpperCase();
  const m = s.match(/^TEST(\d+)-/);
  if (m) return parseInt(m[1], 10);
  if (s.startsWith("TEST-")) return 1;
  return null;
}
function viewRoundOf(pid) {
  return isTestProductId(pid) ? { mode: "TEST", round: getTestRoundFromProductId(pid) || 1 } : { mode: "OFFICIAL", round: null };
}
// isEventInViewRound
function isEventInViewRound(r, vr) {
  if (!r || r.status !== "COMPLETED") return false;
  const isT = isTestProductId(r.product_id);
  if (vr.mode === "OFFICIAL") return !isT;
  if (!isT) return false;
  return (getTestRoundFromProductId(r.product_id) || 1) === vr.round;
}
// fetchAndResolveFlowsForRound 的候選順序（正式實作時老師用「目前測試次數」往回找，這裡用 10 往回找）
function resolveFlow(group, vr) {
  const byKey = {};
  flows.forEach((f) => { const k = (f.group_id || "").trim(); (byKey[k] = byKey[k] || []).push(f); });
  const flowKey = vr.mode === "OFFICIAL" ? `${group}-OFFICIAL` : `${group}-T${vr.round}`;
  const cand = [flowKey];
  if (vr.mode === "TEST" && vr.round > 1) for (let r = vr.round - 1; r >= 1; r--) cand.push(`${group}-T${r}`);
  else if (vr.mode === "OFFICIAL") for (let r = 10; r >= 1; r--) cand.push(`${group}-T${r}`);
  if (!cand.includes(group)) cand.push(group);
  for (const k of cand) if (byKey[k] && byKey[k].length) return byKey[k];
  return [];
}

// showStats（每站統計 + 產線 Cycle Time），只拿掉畫面相關的程式
function showStats(data, group, vr) {
  const rows = data.filter((r) => (r.group_id || "").trim() === group && isEventInViewRound(r, vr));
  const allStartTimes = rows.map((r) => new Date(r.start_time).getTime()).filter((t) => !isNaN(t));
  const lineStartTime = allStartTimes.length > 0 ? Math.min(...allStartTimes) : null;
  const stationEvents = {};
  rows.forEach((r) => { const st = r.station_id ?? "(未知)"; (stationEvents[st] = stationEvents[st] || []).push(r); });
  const stats = {};
  const stationKeys = Object.keys(stationEvents).sort((a, b) => a.localeCompare(b));
  stationKeys.forEach((station) => {
    const evs = stationEvents[station].slice().sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
    let runSum = 0, waitSum = 0;
    evs.forEach((r, idx) => {
      runSum += Number(r.duration_sec) || 0;
      if (idx === 0) {
        const curStart = new Date(r.start_time).getTime();
        if (lineStartTime !== null && !isNaN(curStart)) {
          const preWait = (curStart - lineStartTime) / 1000;
          if (preWait > 0 && preWait < 600) waitSum += preWait;
        }
      } else {
        const prevFinish = new Date(evs[idx - 1].finish_time).getTime();
        const curStart = new Date(r.start_time).getTime();
        if (!isNaN(prevFinish) && !isNaN(curStart)) {
          const gap = (curStart - prevFinish) / 1000;
          if (gap > 0 && gap < 600) waitSum += gap;
        }
      }
    });
    stats[station] = { qty: evs.length, runSum, waitSum };
  });
  let maxAvgCycle = 0, bottleneckStation = null;
  stationKeys.forEach((station) => {
    const s = stats[station];
    const avg = s.qty > 0 ? s.runSum / s.qty : 0;
    s.avgCycle = avg;
    if (s.qty > 0 && avg > maxAvgCycle) { maxAvgCycle = avg; bottleneckStation = station; }
  });
  // 終點站
  const groupFlows = resolveFlow(group, vr);
  let finalStationId = null;
  if (groupFlows.length > 0) {
    const allFlowSt = new Set();
    groupFlows.forEach((f) => { if (f.station_id) allFlowSt.add(f.station_id.trim()); if (f.next_station_id) allFlowSt.add(f.next_station_id.trim()); });
    const terminals = Array.from(allFlowSt).filter((st) => !groupFlows.some((f) => (f.station_id || "").trim() === st && (f.next_station_id || "").trim() !== ""));
    if (terminals.length > 0) { terminals.sort((a, b) => a.localeCompare(b)); finalStationId = terminals[terminals.length - 1]; }
  }
  if (!finalStationId && stationKeys.length > 0) finalStationId = stationKeys[stationKeys.length - 1];
  const runStKeys = stationKeys;
  let outputSourceStation = finalStationId, isTerminalOutput = true, activityOutputSets = 0;
  if (finalStationId && stationEvents[finalStationId] && stationEvents[finalStationId].length > 0) {
    activityOutputSets = stationEvents[finalStationId].length;
  } else if (runStKeys.length > 0) {
    outputSourceStation = runStKeys[runStKeys.length - 1];
    activityOutputSets = stationEvents[outputSourceStation].length;
    isTerminalOutput = outputSourceStation === finalStationId;
  }
  const runFinishes = rows.map((r) => new Date(r.finish_time).getTime()).filter((t) => !isNaN(t));
  const maxFinishMs = runFinishes.length ? Math.max(...runFinishes) : null;
  const activityTotalSec = lineStartTime !== null && maxFinishMs !== null && maxFinishMs >= lineStartTime ? (maxFinishMs - lineStartTime) / 1000 : 0;
  const activityTaktSec = activityOutputSets > 0 && activityTotalSec > 0 ? activityTotalSec / activityOutputSets : null;
  const station_stats = {};
  stationKeys.forEach((st) => {
    const s = stats[st];
    const denom = s.runSum + s.waitSum;
    station_stats[st] = { qty: s.qty, avg_ct: s.avgCycle, wait_sec: s.waitSum, util_pct: denom > 0 ? (s.runSum / denom) * 100 : 0,
      // 「與本次 Cycle Time 比較」欄：佔 Cycle Time %、差幾秒（老師 showStats 第 2959–2963 行）
      pct_of_line: activityTaktSec ? (s.avgCycle / activityTaktSec) * 100 : null,
      vs_line_sec: activityTaktSec ? s.avgCycle - activityTaktSec : null };
  });
  return {
    events: rows.length, final_station: finalStationId, output_station: outputSourceStation,
    terminal_reached: isTerminalOutput, output_sets: activityOutputSets, total_sec: activityTotalSec,
    takt_sec: activityTaktSec, bottleneck: bottleneckStation, bottleneck_ct: maxAvgCycle, station_stats,
  };
}

const lines = {};
events.forEach((e) => {
  if (e.status !== "COMPLETED") return;
  const vr = viewRoundOf(e.product_id);
  const key = `${(e.group_id || "").trim()}|${vr.mode === "OFFICIAL" ? "FORMAL" : "TEST" + vr.round}`;
  lines[key] = lines[key] || { group: (e.group_id || "").trim(), vr };
});
const out = {};
Object.entries(lines).forEach(([k, v]) => { out[k] = showStats(events, v.group, v.vr); });
process.stdout.write(JSON.stringify(out));
