"""FastAPI：開始／停止／狀態／結果 API + 約每 5 秒執行一次的 Python 模擬迴圈。

本機啟動（不需要 Supabase，會用 Excel 資料「重播」生產過程）：
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import MemoryStore, make_store, now_iso
from excel_loader import load_events
from simulation import compute

log = logging.getLogger("sim")
logging.basicConfig(level=logging.INFO)

store = make_store()

INTERVAL = float(os.getenv("SIM_INTERVAL_SECONDS", "5"))
MAX_RUN_MINUTES = float(os.getenv("MAX_RUN_MINUTES", "90"))       # 課堂結束自動停止
LIVE = store.mode in ("supabase", "supabase-read")  # 讀真正的 Supabase event 表
EVENT_TABLE = os.getenv("EVENT_TABLE", "event" if LIVE else "event_replay")
# REPLAY=true：每一輪把 Excel 的下一批事件寫進 EVENT_TABLE，模擬「現場正在生產」
REPLAY = os.getenv("REPLAY", "false" if LIVE else "true").lower() == "true" and store.mode != "supabase-read"
REPLAY_BATCH = int(os.getenv("REPLAY_BATCH", "5"))
# true：event 表沒有變化時不寫結果（避免灌爆結果表）；記憶體模式預設每 5 秒都寫一筆
ONLY_ON_NEW_DATA = os.getenv("ONLY_ON_NEW_DATA", "true" if LIVE else "false").lower() == "true"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

_excel: list[dict] | None = None
_task: asyncio.Task | None = None
_lock = asyncio.Lock()


def excel_events() -> list[dict]:
    global _excel
    if _excel is None:
        # 轉成 JSON 可序列化（時間轉字串、移除空的 part_no）
        _excel = json.loads(json.dumps(load_events(), default=str))
    return _excel


async def run_loop(run_id: str) -> None:
    st = await store.get_status()
    tick = int(st.get("tick") or 0)
    pos = int(st.get("replay_pos") or 0)
    started_dt = datetime.fromisoformat(str(st.get("started_at") or now_iso()).replace("Z", "+00:00"))
    last_sig = None
    checked = 0
    log.info("run %s: table=%s replay=%s tick=%s pos=%s", run_id, EVENT_TABLE, REPLAY, tick, pos)

    while True:
        t0 = asyncio.get_running_loop().time()
        try:
            if (datetime.now(timezone.utc) - started_dt).total_seconds() > MAX_RUN_MINUTES * 60:
                await store.add_result({"run_id": run_id, "tick": tick, "message": f"已超過 {MAX_RUN_MINUTES:g} 分鐘，自動停止模擬"})
                await store.save_status(running=False, message="自動停止（超過時間上限）")
                return

            if REPLAY and pos < len(excel_events()):
                batch = excel_events()[pos : pos + REPLAY_BATCH]
                await store.add_events(EVENT_TABLE, [{k: v for k, v in e.items() if k != "part_no"} for e in batch])
                pos += len(batch)

            events = await store.fetch_events(EVENT_TABLE)
            sig = (len(events), max((str(e.get("finish_time")) for e in events), default=None))
            checked += 1
            if sig == last_sig and ONLY_ON_NEW_DATA:
                # 沒有新資料：不重算、不寫結果，只更新「最後檢查」
                await store.save_status(running=True, last_check_at=now_iso(),
                                        last_check=f"第 {checked} 次檢查：{len(events)} 筆，沒有新資料")
            else:
                last_sig = sig
                tick += 1
                message, data = compute(tick, events)
                if REPLAY:
                    message += f"（重播進度 {pos}/{len(excel_events())}）"
                await store.add_result({"run_id": run_id, "tick": tick, "message": message, "data": data})
                await store.save_status(running=True, run_id=run_id, tick=tick, replay_pos=pos, message=message,
                                        last_check_at=now_iso(),
                                        last_check=f"第 {checked} 次檢查：{len(events)} 筆，有新資料 → 已重新計算")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # 網路錯誤等不要讓整個迴圈掛掉
            log.exception("tick failed")
            try:
                await store.save_status(message=f"錯誤：{e}")
            except Exception:
                pass
        await asyncio.sleep(max(0.5, INTERVAL - (asyncio.get_running_loop().time() - t0)))


def _start_task(run_id: str) -> None:
    global _task
    _task = asyncio.create_task(run_loop(run_id))


def _running() -> bool:
    return _task is not None and not _task.done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服務重啟恢復：資料庫狀態是 running 就接著跑（暫停中的維持暫停）
    try:
        st = await store.get_status()
        if st.get("running"):
            _start_task(st.get("run_id") or "resumed")
    except Exception:
        log.exception("resume failed")
    yield
    if _running():
        _task.cancel()


app = FastAPI(title="Python 課堂模擬 API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])


def check_token(token: str | None) -> None:
    if ADMIN_TOKEN and token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="管理密碼錯誤")


@app.get("/")
async def root():
    return {"ok": True, "service": "python-sim", "store": store.mode, "docs": "/docs"}


@app.get("/health")
async def health():
    return {"ok": True, "store": store.mode, "running": _running(), "time": now_iso()}


@app.get("/status")
async def status():
    st = await store.get_status()
    return {**st, "running": _running(), "paused": bool(st.get("paused")) and not _running(), "store": store.mode, "interval": INTERVAL,
            "event_table": EVENT_TABLE, "replay": REPLAY}


async def _cancel_task() -> bool:
    """停掉計算迴圈並等它真的結束；回傳原本是否在跑。"""
    if not _running():
        return False
    _task.cancel()
    await asyncio.gather(_task, return_exceptions=True)
    return True


@app.post("/start")
async def start(x_admin_token: str | None = Header(default=None)):
    check_token(x_admin_token)
    async with _lock:
        if _running():
            return {"ok": True, "already_running": True}
        st = await store.get_status()
        if st.get("paused"):
            raise HTTPException(status_code=409, detail="模擬目前暫停中，請按「繼續模擬」，或先按「停止模擬」再重新開始")
        run_id = datetime.now(timezone.utc).strftime("%m%d-%H%M%S")
        if REPLAY and (isinstance(store, MemoryStore) or EVENT_TABLE != "event"):
            await store.clear_events(EVENT_TABLE)  # 重播從頭開始（絕不清老師的正式 event 表）
        await store.save_status(running=True, paused=False, paused_at=None, run_id=run_id, tick=0,
                                replay_pos=0, started_at=now_iso(), message="模擬啟動中…")
        await store.add_result({"run_id": run_id, "tick": 0, "message": "Hello from Python！模擬已啟動"})
        _start_task(run_id)
        return {"ok": True, "run_id": run_id}


@app.post("/pause")
async def pause(x_admin_token: str | None = Header(default=None)):
    """暫停：停止計算，但保留執行次數、重播進度與 run_id。"""
    check_token(x_admin_token)
    async with _lock:
        if not await _cancel_task():
            raise HTTPException(status_code=409, detail="目前沒有正在執行的模擬")
        st = await store.get_status()
        msg = f"模擬已暫停（第 {st.get('tick')} 次執行後）"
        await store.save_status(running=False, paused=True, paused_at=now_iso(), message=msg)
        await store.add_result({"run_id": st.get("run_id"), "tick": st.get("tick"), "message": msg})
        return {"ok": True, "tick": st.get("tick")}


@app.post("/resume")
async def resume(x_admin_token: str | None = Header(default=None)):
    """繼續：從暫停的地方接著跑；暫停的時間不算進 MAX_RUN_MINUTES。"""
    check_token(x_admin_token)
    async with _lock:
        if _running():
            return {"ok": True, "already_running": True}
        st = await store.get_status()
        if not st.get("paused"):
            raise HTTPException(status_code=409, detail="目前沒有暫停中的模擬（Render 休眠重啟後進度會清空，請重新開始）")
        now = datetime.now(timezone.utc)
        started = datetime.fromisoformat(str(st.get("started_at") or now_iso()).replace("Z", "+00:00"))
        paused_at = datetime.fromisoformat(str(st.get("paused_at") or now_iso()).replace("Z", "+00:00"))
        started += now - paused_at
        msg = f"模擬繼續（從第 {st.get('tick')} 次之後接著跑）"
        await store.save_status(running=True, paused=False, paused_at=None,
                                started_at=started.isoformat(), message=msg)
        await store.add_result({"run_id": st.get("run_id"), "tick": st.get("tick"), "message": msg})
        _start_task(st.get("run_id") or "resumed")
        return {"ok": True, "tick": st.get("tick")}


@app.post("/stop")
async def stop(x_admin_token: str | None = Header(default=None)):
    check_token(x_admin_token)
    async with _lock:
        st = await store.get_status()
        was = await _cancel_task() or bool(st.get("paused"))
        await store.save_status(running=False, paused=False, paused_at=None, message="模擬已停止")
        if was:
            await store.add_result({"run_id": st.get("run_id"), "tick": st.get("tick"), "message": "模擬已停止"})
        return {"ok": True, "was_running": was}


@app.get("/results")
async def results(limit: int = 20):
    return await store.latest_results(min(max(limit, 1), 200))
