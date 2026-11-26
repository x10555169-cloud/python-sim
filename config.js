// ===== 只要改這個檔案 =====
window.APP_CONFIG = {
  // 資料來源：
  //   "static"   只需要 GitHub：顯示 GitHub Actions 上 Python 算好的 data/results.json（目標一、二）
  //   "api"      網頁直接連 FastAPI（本機測試，或 Render 部署好但沒有 Supabase）
  //   "supabase" 開始/停止走 FastAPI，結果從 Supabase 讀（Word 文件的完整架構）
  //   "browser"  不用 Render：網頁直接用 API 讀資料庫（下面的 SUPABASE_URL / KEY），Python 在瀏覽器裡執行
  MODE: "browser",

  // FastAPI 網址：本機 "http://localhost:8000"；Render 例如 "https://python-sim-api.onrender.com"
  API_BASE: "https://python-sim-api.onrender.com",

  // Supabase 專案網址，例如 "https://abcdxyz.supabase.co"（MODE = "browser" 或 "supabase" 才需要）
  // 換資料庫（例如換成甲班）：MODE = "browser" 時只要改這兩行；老師的 API Dashboard（api.html）要另外改它檔案裡的兩行
  SUPABASE_URL: "https://iomsrjkrvuzrsluirtdj.supabase.co",
  // publishable key 可以公開放在前端（RLS 只允許讀取）
  SUPABASE_KEY: "sb_publishable_QmLToEOs4wEEPBnASz0dxg_o0hhtgLO",

  // 老師的現場系統（計時器、QR Code、監控中心）網址：網頁上各組的連結會指到這裡
  TEACHER_SITE: "https://lctsaio365.github.io/Class_A/",

  // 場次紀錄（勾選場次、是否通過）：要先在資料庫執行 round_selection.sql 建表才打開
  ENABLE_ROUND_RECORDS: false,

  POLL_MS: 3000,
};
