from __future__ import annotations

import asyncio
import time
from pydantic import BaseModel

from cache import CacheClient
from db import Database
from metrics import MetricsStore


class ItemResponse(BaseModel):
    item_id: int
    value: str


class UpsertRequest(BaseModel):
    value: str


class WriteBackService:
    strategy_name = "write-back"

    def __init__(
        self,
        database: Database,
        cache: CacheClient,
        metrics: MetricsStore,
        flush_seconds: float,
    ) -> None:
        self.database = database
        self.cache = cache
        self.metrics = metrics
        self.flush_seconds = flush_seconds
        self._stop_event = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._stop_event.clear()
        self._worker = asyncio.create_task(self._flush_worker())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._worker is not None:
            await self._worker
        await self.flush_now()

    async def read_item(self, item_id: int) -> ItemResponse:
        started_at = time.perf_counter()
        key = self.cache.key(self.strategy_name, item_id)

        cached_value = await self.cache.get(key)
        if cached_value is not None:
            await self.metrics.add_cache_hit(self.strategy_name)
            latency_ms = (time.perf_counter() - started_at) * 1000
            await self.metrics.add_request(self.strategy_name, latency_ms)
            return ItemResponse(item_id=item_id, value=cached_value)

        await self.metrics.add_cache_miss(self.strategy_name)
        item = await self.database.get_item(item_id)
        await self.metrics.add_db_hit(self.strategy_name)
        if item is None:
            latency_ms = (time.perf_counter() - started_at) * 1000
            await self.metrics.add_request(self.strategy_name, latency_ms)
            return ItemResponse(item_id=item_id, value="")

        await self.cache.set(key, item.value)
        await self.metrics.add_cache_write(self.strategy_name)

        latency_ms = (time.perf_counter() - started_at) * 1000
        await self.metrics.add_request(self.strategy_name, latency_ms)
        return ItemResponse(item_id=item.item_id, value=item.value)

    async def write_item(self, item_id: int, payload: UpsertRequest) -> ItemResponse:
        started_at = time.perf_counter()

        key = self.cache.key(self.strategy_name, item_id)
        await self.cache.set(key, payload.value)
        await self.metrics.add_cache_write(self.strategy_name)
        await self.cache.add_dirty_id(item_id)

        latency_ms = (time.perf_counter() - started_at) * 1000
        await self.metrics.add_request(self.strategy_name, latency_ms)
        return ItemResponse(item_id=item_id, value=payload.value)

    async def flush_now(self) -> int:
        dirty_ids = await self.cache.pop_all_dirty_ids()
        if not dirty_ids:
            return 0

        writes_count = 0
        for item_id in dirty_ids:
            key = self.cache.key(self.strategy_name, item_id)
            value = await self.cache.get(key)
            if value is None:
                continue
            await self.database.upsert_item(item_id, value)
            await self.metrics.add_db_write(self.strategy_name)
            writes_count += 1
        return writes_count

    async def _flush_worker(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(self.flush_seconds)
            await self.flush_now()
