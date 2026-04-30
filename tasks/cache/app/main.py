from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from cache import CacheClient
from db import Database
from metrics import MetricsStore
from strategies.cache_aside import CacheAsideService, UpsertRequest as LazyUpsertRequest
from strategies.write_back import WriteBackService, UpsertRequest as WriteBackUpsertRequest
from strategies.write_through import WriteThroughService, UpsertRequest as WriteThroughUpsertRequest


def read_env() -> dict[str, str | int | float]:
    return {
        "db_host": os.getenv("DB_HOST", "db"),
        "db_port": int(os.getenv("DB_PORT", "5432")),
        "db_name": os.getenv("DB_NAME", "cache_demo"),
        "db_user": os.getenv("DB_USER", "cache_user"),
        "db_password": os.getenv("DB_PASSWORD", "cache_password"),
        "redis_host": os.getenv("REDIS_HOST", "cache"),
        "redis_port": int(os.getenv("REDIS_PORT", "6379")),
        "write_back_flush_seconds": float(os.getenv("WRITE_BACK_FLUSH_SECONDS", "2")),
    }


class MetricsView(BaseModel):
    strategy: str
    requests: int
    latency_ms_sum: float
    avg_latency_ms: float
    db_hits: int
    db_writes: int
    cache_hits: int
    cache_misses: int
    cache_writes: int
    cache_hit_rate: float


env = read_env()

database = Database(
    host=env["db_host"],
    port=env["db_port"],
    name=env["db_name"],
    user=env["db_user"],
    password=env["db_password"],
)
cache = CacheClient(host=env["redis_host"], port=env["redis_port"])
metrics = MetricsStore()
lazy_service = CacheAsideService(database=database, cache=cache, metrics=metrics)
write_through_service = WriteThroughService(database=database, cache=cache, metrics=metrics)
write_back_service = WriteBackService(
    database=database,
    cache=cache,
    metrics=metrics,
    flush_seconds=env["write_back_flush_seconds"],
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.connect()
    await database.init_schema()
    await write_back_service.start()
    yield
    await write_back_service.stop()
    await cache.close()
    await database.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/seed")
async def seed() -> dict[str, int]:
    await database.init_schema()
    await database.seed_items(total=100)
    await reset_strategy("lazy")
    await reset_strategy("write-through")
    await reset_strategy("write-back")
    return {"seeded_rows": 100}


@app.get("/lazy/items/{item_id}")
async def lazy_read(item_id: int):
    return await lazy_service.read_item(item_id)


@app.post("/lazy/items/{item_id}")
async def lazy_write(item_id: int, payload: LazyUpsertRequest):
    return await lazy_service.write_item(item_id, payload)


@app.get("/write-through/items/{item_id}")
async def write_through_read(item_id: int):
    return await write_through_service.read_item(item_id)


@app.post("/write-through/items/{item_id}")
async def write_through_write(item_id: int, payload: WriteThroughUpsertRequest):
    return await write_through_service.write_item(item_id, payload)


@app.get("/write-back/items/{item_id}")
async def write_back_read(item_id: int):
    return await write_back_service.read_item(item_id)


@app.post("/write-back/items/{item_id}")
async def write_back_write(item_id: int, payload: WriteBackUpsertRequest):
    return await write_back_service.write_item(item_id, payload)


@app.post("/flush/write-back")
async def flush_write_back() -> dict[str, int]:
    flushed_writes = await write_back_service.flush_now()
    return {"flushed_writes": flushed_writes}


@app.get("/metrics/{strategy}", response_model=MetricsView)
async def strategy_metrics(strategy: str):
    snapshot = await metrics.snapshot(strategy)
    return MetricsView(strategy=strategy, **snapshot)


@app.post("/metrics/{strategy}/reset")
async def reset_strategy(strategy: str) -> dict[str, str]:
    await metrics.reset(strategy)
    await cache.delete_prefix(f"{strategy}:")
    if strategy == "write-back":
        await cache.delete_prefix("write-back:dirty")
    return {"status": "reset"}
