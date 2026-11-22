"""後端首頁（Render 網址打開看到的頁面）：運作狀態 + 所有連結 + API 說明。"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

TW = timezone(timedelta(hours=8))

ENDPOINTS = [
    ("GET", "/health", "健康檢查：服務是否活著、用哪種資料模式"),
    ("GET", "/status", "模擬狀態：執行中／暫停／停止、執行次數、最後檢查"),
    ("GET", "/results?limit=20", "最近的計算結果（網頁就是讀這個）"),
    ("POST", "/start", "開始模擬"),
    ("POST", "/pause", "暫停模擬（保留進度）"),
    ("POST", "/resume", "繼續模擬"),
    ("POST", "/stop", "停止模擬"),
]

MODE_LABEL = {
    "supabase": "Supabase 完整模式（讀 event、結果寫回資料庫）",
    "supabase-read": "Supabase 唯讀模式（讀 event，結果存在 Render 記憶體）",
    "memory": "記憶體模式（用 Excel 重播，未連資料庫）",
}


def _tw(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(TW).strftime("%Y/%m/%d %H:%M:%S")
    except ValueError:
        return str(iso)


def render(*, status: dict, latest: dict | None, mode: str, db_host: str, event_table: str,
           interval: float, frontend_url: str, repo_url: str) -> str:
    e = html.escape
    state = "執行中" if status.get("running") else "已暫停" if status.get("paused") else "已停止"
    state_cls = {"執行中": "run", "已暫停": "pause", "已停止": "stop"}[state]
    data = (latest or {}).get("data") or {}
    docs_url = frontend_url.rstrip("/") + "/docs.html"
    rows = "".join(
        f'<tr><td><span class="m m-{m.lower()}">{m}</span></td>'
        f'<td><code>{e(p)}</code></td><td>{e(d)}</td></tr>' for m, p, d in ENDPOINTS)
    facts = [
        ("模擬狀態", f'<span class="pill {state_cls}">{state}</span>'),
        ("執行次數", e(str(status.get("tick", 0)))),
        ("最後檢查", e(_tw(status.get("last_check_at"))) + (f'<br><small>{e(status.get("last_check") or "")}</small>' if status.get("last_check") else "")),
        ("資料模式", e(MODE_LABEL.get(mode, mode))),
        ("資料庫", e(db_host or "未設定")),
        ("資料表", f"<code>{e(event_table)}</code>"),
        ("檢查間隔", f"{interval:g} 秒"),
        ("最新資料", f'{e(str(data.get("events", "—")))} 筆事件、{e(str(data.get("groups", "—")))} 組'),
    ]
    facts_html = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in facts)
    msg = e((latest or {}).get("message") or "目前還沒有計算結果")
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="15">
<title>Python 模擬後端</title>
<style>
:root{{--bg:#f3f5f7;--card:#fff;--fg:#18212b;--muted:#5b6876;--line:#dde3e9;--accent:#2f5d86;--ok:#2f8f5b;--warn:#c98a0c;--bad:#b3433a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#11161c;--card:#18202a;--fg:#e4e9ee;--muted:#9aa7b4;--line:#2a3542;--accent:#7fb0dc;--ok:#5cc28c;--warn:#f2b739;--bad:#e2766c;color-scheme:dark}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 "Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;padding:0 16px 40px}}
main{{max-width:900px;margin:auto;display:grid;gap:16px}}
header{{padding:28px 0 4px}} h1{{margin:0;font-size:24px}} .sub{{color:var(--muted);margin:4px 0 0}}
h2{{font-size:16px;margin:0 0 12px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}}
.links{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}}
.links a{{display:block;padding:12px 14px;border:1px solid var(--line);border-radius:10px;text-decoration:none;color:var(--fg)}}
.links a:hover{{border-color:var(--accent)}} .links b{{display:block;color:var(--accent)}} .links span{{font-size:13px;color:var(--muted);overflow-wrap:anywhere}}
dl{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;margin:0}}
dl div{{border:1px solid var(--line);border-radius:8px;padding:8px 10px}} dt{{font-size:12px;color:var(--muted)}} dd{{margin:0;font-weight:600;overflow-wrap:anywhere}}
small{{font-weight:400;color:var(--muted)}}
.pill{{display:inline-block;padding:0 10px;border-radius:999px;border:1px solid currentColor;font-size:13px}}
.run{{color:var(--ok)}} .pause{{color:var(--warn)}} .stop{{color:var(--muted)}}
.msg{{margin:0;font-size:16px;overflow-wrap:anywhere}}
.tbl{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}} th{{color:var(--muted);font-weight:500}}
code{{font-family:ui-monospace,Consolas,monospace;font-size:13px}}
.m{{font:600 11px/1 ui-monospace,monospace;padding:3px 6px;border-radius:4px;color:#fff}} .m-get{{background:var(--ok)}} .m-post{{background:var(--accent)}}
footer{{color:var(--muted);font-size:13px}}
</style></head><body><main>
<header><h1>Python 模擬後端</h1>
<p class="sub">Render 雲端主機上的 FastAPI + Python。每 {interval:g} 秒讀取資料庫，有新資料才重新計算。本頁每 15 秒自動更新。</p></header>

<section class="card"><h2>連結</h2><div class="links">
<a href="{e(frontend_url)}" target="_blank" rel="noopener"><b>前端網頁</b><span>{e(frontend_url)}</span></a>
<a href="/docs" target="_blank" rel="noopener"><b>API 文件（可直接測試）</b><span>/docs</span></a>
<a href="{e(docs_url)}" target="_blank" rel="noopener"><b>系統說明</b><span>資料統整、演算法、程式碼</span></a>
<a href="{e(repo_url)}" target="_blank" rel="noopener"><b>GitHub 程式碼</b><span>{e(repo_url)}</span></a>
</div></section>

<section class="card"><h2>運作狀態</h2><dl>{facts_html}</dl></section>

<section class="card"><h2>Python 最新訊息</h2><p class="msg">{msg}</p>
<p class="sub">計算時間：{e(_tw((latest or {}).get("created_at")))}</p></section>

<section class="card"><h2>API 一覽</h2><div class="tbl"><table>
<thead><tr><th>方法</th><th>網址</th><th>功能</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="sub">設定了 ADMIN_TOKEN 時，POST 需要帶標頭 <code>X-Admin-Token</code>。</p></section>

<footer>頁面產生時間：{datetime.now(TW).strftime("%Y/%m/%d %H:%M:%S")}（台灣時間）</footer>
</main></body></html>"""
