from __future__ import annotations

import asyncpg
from pydantic import BaseModel


class ItemRecord(BaseModel):
    item_id: int
    value: str


class Database:
    def __init__(self, host: str, port: int, name: str, user: str, password: str) -> None:
        self._dsn = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=10)

    async def close(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()

    async def init_schema(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
        await self._execute(query)

    async def seed_items(self, total: int = 100) -> None:
        await self._execute("TRUNCATE TABLE items")
        rows = [(idx, f"seed_value_{idx}") for idx in range(1, total + 1)]
        if not rows:
            return

        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.executemany("INSERT INTO items(id, value) VALUES($1, $2)", rows)

    async def get_item(self, item_id: int) -> ItemRecord | None:
        row = await self._fetchrow("SELECT id, value FROM items WHERE id = $1", item_id)
        if row is None:
            return None
        return ItemRecord(item_id=row["id"], value=row["value"])

    async def upsert_item(self, item_id: int, value: str) -> None:
        await self._execute(
            """
            INSERT INTO items(id, value)
            VALUES($1, $2)
            ON CONFLICT(id)
            DO UPDATE SET value = EXCLUDED.value
            """,
            item_id,
            value,
        )

    async def _execute(self, query: str, *args: object) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(query, *args)

    async def _fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
