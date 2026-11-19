"""最簡單的「目標一」測試：不用 Render，直接從任何一台電腦用 Python 送一段文字到 Supabase，
網頁（GitHub Pages）上就會看到。

    pip install httpx
    set SUPABASE_URL=https://xxxx.supabase.co        (Mac/Linux 用 export)
    set SUPABASE_SECRET_KEY=sb_secret_xxxx
    python send_message.py "Hello from Python"
"""
import asyncio
import sys

from database import SupabaseStore, make_store


async def main() -> None:
    text = " ".join(sys.argv[1:]) or "Hello from Python！"
    store = make_store()
    if not isinstance(store, SupabaseStore):
        sys.exit("請先設定環境變數 SUPABASE_URL 與 SUPABASE_SECRET_KEY")
    row = await store.add_result({"run_id": "manual", "tick": 0, "message": text})
    print("已送出：", row)


if __name__ == "__main__":
    asyncio.run(main())
