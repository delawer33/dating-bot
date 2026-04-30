from __future__ import annotations

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


class CacheAsideService:
    strategy_name = "lazy"

    def __init__(self, database: Database, cache: CacheClient, metrics: MetricsStore) -> None:
        self.database = database
        self.cache = cache
        self.metrics = metrics

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

        await self.database.upsert_item(item_id, payload.value)
        await self.metrics.add_db_write(self.strategy_name)

        latency_ms = (time.perf_counter() - started_at) * 1000
        await self.metrics.add_request(self.strategy_name, latency_ms)
        return ItemResponse(item_id=item_id, value=payload.value)
