"""備份 Supabase 資料（用 publishable key 能讀到的表）→ Excel + CSV + JSON。

    pip install httpx openpyxl
    python backup_supabase.py <SUPABASE_URL> <publishable 或 secret key> [輸出資料夾] [班級名稱]

例：python backup_supabase.py https://xxxx.supabase.co sb_publishable_xxx backups 甲班

注意：這只備份「資料」，不含資料表結構、權限 (RLS)、帳號等；完整備份請由資料庫擁有者在
Supabase 後台操作（Database → Backups，或 Table Editor → Export to CSV）。
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import openpyxl
from openpyxl.styles import Font

# publishable key 無法列出所有資料表，只能逐一嘗試常見名稱
CANDIDATE_TABLES = [
    "event", "events", "product", "products", "station", "stations", "group", "groups",
    "student", "students", "users", "profiles", "orders", "parts", "settings", "config",
    "logs", "sim_results", "sim_status", "event_replay",
]
TW = timezone(timedelta(hours=8))


def fetch_table(client: httpx.Client, table: str) -> list[dict] | None:
    rows: list[dict] = []
    while True:
        r = client.get(f"/{table}", params={"select": "*", "limit": 1000, "offset": len(rows)})
        if r.status_code in (401, 403, 404):
            return None  # 不存在或沒有讀取權限
        r.raise_for_status()
        page = r.json()
        rows += page
        if len(page) < 1000:
            return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig：Excel 開中文不亂碼
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def add_sheet(wb: openpyxl.Workbook, title: str, rows: list[dict]) -> None:
    ws = wb.create_sheet(title[:31])
    cols = list(dict.fromkeys(k for r in rows for k in r))
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in (r.get(c) for c in cols)])
    ws.freeze_panes = "A2"


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    url, key = sys.argv[1].rstrip("/"), sys.argv[2]
    out_root = Path(sys.argv[3] if len(sys.argv) > 3 else "backups")
    label = sys.argv[4] if len(sys.argv) > 4 else url.split("//")[1].split(".")[0]
    stamp = datetime.now(TW).strftime("%Y%m%d_%H%M")
    out = out_root / f"{label}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    headers = {"apikey": key}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    client = httpx.Client(base_url=f"{url}/rest/v1", headers=headers, timeout=30)

    found: dict[str, list[dict]] = {}
    for t in CANDIDATE_TABLES:
        rows = fetch_table(client, t)
        if rows is not None:
            found[t] = rows
            print(f"  {t}: {len(rows)} 筆")
    if not found:
        sys.exit("沒有讀到任何資料表（可能是 key 錯誤或 RLS 不允許讀取）")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    info = wb.create_sheet("備份資訊")
    info.append(["備份時間（台灣）", datetime.now(TW).strftime("%Y-%m-%d %H:%M:%S")])
    info.append(["資料庫", url])
    info.append(["班級", label])
    for t, rows in found.items():
        info.append([f"資料表 {t}", f"{len(rows)} 筆"])

    for t, rows in found.items():
        (out / f"{t}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        if rows:
            write_csv(out / f"{t}.csv", rows)
            add_sheet(wb, t, sorted(rows, key=lambda r: str(r.get("start_time") or r.get("created_at") or "")))

    # event 另外依組別分頁（同老師 Excel 的格式：每組一個工作表）
    ev = found.get("event") or []
    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in ev:
        by_group[str(r.get("group_id"))].append(r)
    for g in sorted(by_group):
        add_sheet(wb, f"event_{g}", sorted(by_group[g], key=lambda r: str(r.get("start_time") or "")))

    xlsx = out / f"{label}_備份_{stamp}.xlsx"
    wb.save(xlsx)
    print(f"完成：{out}")


if __name__ == "__main__":
    main()
