// ===== 只要改這個檔案 =====
window.APP_CONFIG = {
  // 資料來源：
  //   "static"   只需要 GitHub：顯示 GitHub Actions 上 Python 算好的 data/results.json（目標一、二）
  //   "api"      網頁直接連 FastAPI（本機測試，或 Render 部署好但沒有 Supabase）
  //   "supabase" 開始/停止走 FastAPI，結果從 Supabase 讀（Word 文件的完整架構）
  MODE: "api",

  // FastAPI 網址：本機 "http://localhost:8000"；Render 例如 "https://python-sim-api.onrender.com"
  API_BASE: "https://python-sim-api.onrender.com",

  // Supabase 專案網址，例如 "https://abcdxyz.supabase.co"（MODE = "supabase" 才需要）
  SUPABASE_URL: "https://fqbsrcbxtmagczykoesv.supabase.co",
  // publishable key 可以公開放在前端（RLS 只允許讀取）
  SUPABASE_KEY: "sb_publishable_mn0CAB_nkrDycq6DS3Q2_g_-80SlWHB",

  // 老師的現場系統（計時器、QR Code、監控中心）網址：網頁上各組的連結會指到這裡
  TEACHER_SITE: "https://lctsaio365.github.io/Class_A/",

  // 場次紀錄（勾選場次、是否通過）：要先在資料庫執行 round_selection.sql 建表才打開
  ENABLE_ROUND_RECORDS: false,

  POLL_MS: 3000,
};
