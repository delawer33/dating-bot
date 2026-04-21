import asyncio
import base64
import json
import os
import time
import uuid

import redis.asyncio as aioredis

from models import BrokerConfig, MessagePayload, RunConfig
from rate_limiter import TokenBucketRateLimiter

STREAM_NAME = "benchmark_stream"
# In Docker Compose use redis://redis:6379. On the host, use localhost:6378 if you map 6378:6379.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6378")


async def _get_client() -> aioredis.Redis:
    return aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
    )


async def run(config: RunConfig, stop_event: asyncio.Event, sent_counter: list[int]) -> None:
    client = await _get_client()

    try:
        if config.config == BrokerConfig.durable_ack:
            await client.config_set("appendonly", "yes")
        else:
            await client.config_set("appendonly", "no")

        raw_bytes = bytes(config.msg_size)
        payload_str = base64.b64encode(raw_bytes).decode()

        limiter = TokenBucketRateLimiter(config.target_rate)
        seq = 0
        deadline = time.monotonic() + config.duration

        while not stop_event.is_set() and time.monotonic() < deadline:
            await limiter.acquire()

            msg = MessagePayload(
                id=str(uuid.uuid4()),
                send_ts=time.monotonic(),
                seq=seq,
                payload=payload_str,
            )

            try:
                await client.xadd(STREAM_NAME, {"data": json.dumps(msg.model_dump())})
                sent_counter[0] += 1
                seq += 1
            except Exception:
                pass

    finally:
        await client.aclose()


async def flush_stream() -> None:
    """Remove the benchmark stream key (deletes entries and consumer groups)."""
    print(f"[flush_stream] connecting REDIS_URL={REDIS_URL!r}", flush=True)
    client = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    try:
        await client.delete(STREAM_NAME)
    finally:
        await client.aclose()
