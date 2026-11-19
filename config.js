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
  SUPABASE_URL: "",
  // publishable key 可以公開放在前端（RLS 只允許讀取）
  SUPABASE_KEY: "sb_publishable_QmLToEOs4wEEPBnASz0dxg_o0hhtgLO",

  POLL_MS: 3000,
};
