"""讀取老師提供的 Excel（每組一個工作表，第一個工作表是欄位說明）。"""
from __future__ import annotations

from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent


def find_xlsx() -> Path:
    """找 Excel：backend/data/ie_chair_data.xlsx，或檔案都放在最外層時的 ie_chair_data.xlsx / 任何 .xlsx"""
    for p in (HERE / "data" / "ie_chair_data.xlsx", HERE / "ie_chair_data.xlsx",
              HERE / "backend" / "data" / "ie_chair_data.xlsx"):
        if p.exists():
            return p
    found = sorted(HERE.glob("*.xlsx")) + sorted((HERE / "data").glob("*.xlsx"))
    if not found:
        raise FileNotFoundError("找不到 Excel 檔（ie_chair_data.xlsx）")
    return found[0]


COLUMNS = [
    "id", "group_id", "product_id", "station_id", "part_no", "wip_before_start",
    "start_time", "finish_time", "duration_sec", "wip_after_finish", "status",
]


def load_events(path: str | Path | None = None) -> list[dict]:
    wb = openpyxl.load_workbook(path or find_xlsx(), read_only=True, data_only=True)
    events: list[dict] = []
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header or header[0] != "id":
            continue  # 跳過「欄位名稱」說明頁
        for r in rows:
            if not r or not r[0]:
                continue
            e = dict(zip(header, r))
            events.append({k: e.get(k) for k in COLUMNS})
    events.sort(key=lambda e: str(e["finish_time"]))
    return events
