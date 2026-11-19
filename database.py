"""Supabase 存取層。

- 有設定 SUPABASE_URL + SUPABASE_SECRET_KEY → 透過 Supabase REST API (PostgREST) 讀寫
- 沒設定 → 使用記憶體模式（本機測試用，重啟即清空）
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

EVENT_COLUMNS = "id,group_id,product_id,station_id,start_time,finish_time,duration_sec,wip_before_start,wip_after_finish,status"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseStore:
    mode = "supabase"

    def __init__(self, url: str, key: str):
        headers = {"apikey": key, "Content-Type": "application/json"}
        # 舊版 service_role 是 JWT（eyJ 開頭）才放 Authorization；新版 sb_secret_ 只放 apikey
        if key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.AsyncClient(base_url=url.rstrip("/") + "/rest/v1", headers=headers, timeout=15)

    async def _get(self, table: str, params: dict) -> list[dict]:
        r = await self.client.get(f"/{table}", params=params)
        r.raise_for_status()
        return r.json()

    async def fetch_events(self, table: str, limit: int = 10000) -> list[dict]:
        return await self._get(table, {"select": EVENT_COLUMNS, "order": "finish_time.asc", "limit": limit})

    async def add_events(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        r = await self.client.post(
            f"/{table}", json=rows, headers={"Prefer": "resolution=merge-duplicates,return=minimal"}
        )
        r.raise_for_status()

    async def clear_events(self, table: str) -> None:
        r = await self.client.delete(f"/{table}", params={"id": "not.is.null"})
        r.raise_for_status()

    async def add_result(self, row: dict) -> dict:
        r = await self.client.post("/sim_results", json=row, headers={"Prefer": "return=representation"})
        r.raise_for_status()
        return r.json()[0]

    async def latest_results(self, limit: int = 20) -> list[dict]:
        return await self._get("sim_results", {"select": "*", "order": "id.desc", "limit": limit})

    async def get_status(self) -> dict:
        rows = await self._get("sim_status", {"select": "*", "id": "eq.1"})
        return rows[0] if rows else {"id": 1, "running": False, "tick": 0, "replay_pos": 0}

    async def save_status(self, **fields: Any) -> None:
        fields = {"id": 1, **fields, "updated_at": now_iso()}
        r = await self.client.post(
            "/sim_status", json=fields, headers={"Prefer": "resolution=merge-duplicates,return=minimal"}
        )
        r.raise_for_status()


class MemoryStore:
    """本機測試用，不需要 Supabase。"""

    mode = "memory"

    def __init__(self):
        self.events: dict[str, list[dict]] = {}
        self.results: list[dict] = []
        self.status: dict = {"id": 1, "running": False, "tick": 0, "replay_pos": 0}

    async def fetch_events(self, table: str, limit: int = 10000) -> list[dict]:
        return sorted(self.events.get(table, []), key=lambda e: str(e["finish_time"]))[:limit]

    async def add_events(self, table: str, rows: list[dict]) -> None:
        cur = {e["id"]: e for e in self.events.get(table, [])}
        cur.update({r["id"]: r for r in rows})
        self.events[table] = list(cur.values())

    async def clear_events(self, table: str) -> None:
        self.events[table] = []

    async def add_result(self, row: dict) -> dict:
        row = {"id": len(self.results) + 1, "created_at": now_iso(), **row}
        self.results.append(row)
        return row

    async def latest_results(self, limit: int = 20) -> list[dict]:
        return list(reversed(self.results[-limit:]))

    async def get_status(self) -> dict:
        return dict(self.status)

    async def save_status(self, **fields: Any) -> None:
        self.status.update(fields, updated_at=now_iso())


def make_store():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    if url and key:
        return SupabaseStore(url, key)
    return MemoryStore()
