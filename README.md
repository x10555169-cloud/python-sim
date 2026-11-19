# Python 課堂模擬：椅子組裝生產線（IE Chair）

資料：`backend/data/ie_chair_data.xlsx`（老師提供的 event 生產歷程，每組一個工作表）。
Python 分析每組、每批次（TEST1/TEST2/正式）的：**各站平均作業秒數、瓶頸站、產線平衡率、完成件數、在製品、每小時產出**。
要換成正式的模擬，只改 `backend/simulation.py` 的 `compute()`。

## 三種部署方式（由簡到繁）

| 方式 | 需要 | 達成 |
|---|---|---|
| **A. 只用 GitHub** | GitHub 帳號 | 目標一、二：GitHub Actions 上的 Python 讀 Excel → 結果顯示在 GitHub Pages |
| B. GitHub + Render | 再加 Render 帳號 | 網頁按「開始模擬」，Python 每 5 秒一輪，即時更新 |
| C. GitHub + Render + Supabase | 再加 Supabase | Word 文件的完整架構（全班共用資料表） |

### A. 只用 GitHub（不用安裝 git）
1. 登入 GitHub → 右上角 **+ → New repository**，名稱例如 `python-sim`，選 **Public** → Create。
2. 在新 repo 頁面點 **uploading an existing file**，把解壓後的**所有檔案與資料夾**拖進去 → Commit。
   （`.github` 資料夾若沒被上傳：點 Add file → Create new file，檔名輸入 `.github/workflows/pages.yml`，貼上內容。）
3. repo → **Settings → Pages → Source 選「GitHub Actions」**。
4. **Actions** 分頁 → 選 *Run Python and deploy to GitHub Pages* → **Run workflow**。
5. 約 1 分鐘後打開 `https://<你的帳號>.github.io/python-sim/`。
   - 「Python 最新訊息」＝ Python 印出的文字（目標一）
   - 「各組生產線分析」＝ Python 從 Excel 抓資料算出的結果（目標二）
   - Actions 的執行紀錄裡也看得到 Python 的 print 輸出。

更新資料：把新的 Excel 上傳覆蓋 `backend/data/ie_chair_data.xlsx`，Actions 會自動重跑。

### B. 加上 Render（即時模擬）
1. Render → New → **Blueprint** → 選這個 repo（讀 `render.yaml`）。不設定 Supabase 時用記憶體模式：
   按「開始模擬」後 Python 每 5 秒把 Excel 的下一批事件「重播」進來並重新計算，模擬現場正在生產。
2. 環境變數 `ALLOWED_ORIGINS` = `https://<你的帳號>.github.io`；可選 `ADMIN_TOKEN`（開始/停止要輸入的密碼）。
3. `frontend/config.js`：`MODE: "api"`、`API_BASE: "https://<render 網址>"`。

### C. 加上 Supabase（Word 文件完整架構）
1. Supabase → SQL Editor → 執行 `supabase/schema.sql`（建立 `event`、`event_replay`、`sim_results`、`sim_status`）。
2. Render 環境變數再加 `SUPABASE_URL`、`SUPABASE_SECRET_KEY`（**secret key 只放這裡**），以及：
   - 讀老師的正式 event 表：`EVENT_TABLE=event`、`REPLAY=false`（預設）
   - 用 Excel 重播測試：`EVENT_TABLE=event_replay`、`REPLAY=true`
3. `frontend/config.js`：`MODE: "supabase"`、填 `SUPABASE_URL`、`API_BASE`。
4. 快速測試（不用 Render）：`python backend/send_message.py "Hello"`，網頁就會出現這段文字。

## 本機測試
```bash
cd backend && pip install -r requirements.txt
python build_static.py              # 方式 A：產生 frontend/data/results.json
uvicorn main:app --port 8000        # 方式 B：本機 API（記憶體 + Excel 重播）
```
```bash
cd frontend && python -m http.server 8080    # 開 http://localhost:8080
```

## 檔案
- `frontend/` index.html、style.css、app.js、**config.js（唯一要改的設定）**、data/results.json
- `backend/simulation.py` 分析/模擬、`excel_loader.py` 讀 Excel、`build_static.py` 方式 A、`main.py` FastAPI、`database.py` Supabase 存取、`send_message.py` 文字測試
- `supabase/schema.sql`、`render.yaml`、`.github/workflows/pages.yml`

## 注意
- 5 秒是目標週期，不是精準排程；Render 免費方案閒置會休眠，第一次啟動要等 30–60 秒，重啟後會依 `sim_status` 自動接續。
- `MAX_RUN_MINUTES`（預設 90）到時自動停止；event 表沒有變化時不寫新結果。
- Python 絕不會清除正式的 `event` 表；重播只清 `event_replay`。
