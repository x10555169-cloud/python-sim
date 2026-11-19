"""讀取老師提供的 Excel（每組一個工作表，第一個工作表是欄位說明）。"""
from __future__ import annotations

from pathlib import Path

import openpyxl

DEFAULT_XLSX = Path(__file__).resolve().parent / "data" / "ie_chair_data.xlsx"
COLUMNS = [
    "id", "group_id", "product_id", "station_id", "part_no", "wip_before_start",
    "start_time", "finish_time", "duration_sec", "wip_after_finish", "status",
]


def load_events(path: str | Path = DEFAULT_XLSX) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
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
