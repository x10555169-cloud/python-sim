"""【只需要 GitHub】由 GitHub Actions 執行：
Python 讀 Excel → 分析 → 寫出 frontend/data/results.json → GitHub Pages 網頁顯示。

本機也可以直接跑：python build_static.py
"""
from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from excel_loader import load_events
from simulation import compute

OUT = Path(__file__).resolve().parent.parent / "frontend" / "data" / "results.json"


def main() -> None:
    events = load_events()
    now = datetime.now(timezone.utc).isoformat()
    where = "GitHub Actions 上" if os.getenv("GITHUB_ACTIONS") else "本機"
    hello = f"Hello from Python {platform.python_version()}！這段文字是{where}的 Python 印出來的"
    print(hello)

    # 模擬「資料一筆一筆進來」：分 5 個時間點計算，網頁的結果紀錄看得到逐步變化
    results = [{"id": 0, "tick": 0, "message": hello, "data": None, "created_at": now}]
    steps = 5
    for i in range(1, steps + 1):
        part = events[: round(len(events) * i / steps)]
        message, data = compute(i, part)
        print(message)
        results.append({"id": i, "tick": i, "message": message, "data": data, "created_at": now})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": {"running": False, "run_id": "github-actions", "tick": steps, "message": results[-1]["message"]},
        "results": list(reversed(results)),
        "generated_at": now,
        "python": sys.version.split()[0],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"已寫出 {OUT}（{len(events)} 筆事件）")


if __name__ == "__main__":
    main()
