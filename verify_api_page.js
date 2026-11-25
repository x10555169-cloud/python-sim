// 從改良版 API 網頁（frontend/api.html）取出「計算核心」，在 Node 裡執行，輸出每條產線的結果 JSON。
// 用法：node verify_api_page.js ../frontend/api.html events.json flows.json
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const core = src.slice(src.indexOf("// ==== CORE START ===="), src.indexOf("// ==== CORE END ===="));
function toTaiwanIso(s) { const d = new Date(s); return new Date(d.getTime() + 8 * 3600e3).toISOString().replace("Z", "+08:00"); }
const RelayDB = { ta1_events: JSON.parse(fs.readFileSync(process.argv[3], "utf8")), ta3_station_flow: JSON.parse(fs.readFileSync(process.argv[4], "utf8")) };
// 跟網頁一樣：時間先換成台灣時間字串
RelayDB.ta1_events = RelayDB.ta1_events.map(r => ({ ...r, start_time: r.start_time && toTaiwanIso(r.start_time), finish_time: r.finish_time && toTaiwanIso(r.finish_time) }));
eval(core + "\nglobalThis.out = buildLines('ALL', 'ALL').map(lineSummary);");
process.stdout.write(JSON.stringify(out));
