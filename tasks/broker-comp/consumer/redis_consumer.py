import asyncio
import json
import os

import redis.asyncio as aioredis

from metrics_store import MetricsStore
from models import BrokerConfig, MessagePayload

STREAM_NAME = "benchmark_stream"
GROUP_NAME = "benchmark_group"
CONSUMER_NAME = "consumer_1"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6378")


async def _ensure_group(client: aioredis.Redis) -> None:
    try:
        await client.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def prepare(config: BrokerConfig) -> None:
    """Ping Redis and create consumer group (durable_ack) before POST /start returns."""
    client = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    try:
        await client.ping()
        if config == BrokerConfig.durable_ack:
            await _ensure_group(client)
    finally:
        await client.aclose()


async def run(config: BrokerConfig, store: MetricsStore, stop_event: asyncio.Event) -> None:
    use_ack = config == BrokerConfig.durable_ack

    client = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
    )

    try:
        if use_ack:
            await _ensure_group(client)

        while not stop_event.is_set():
            try:
                if use_ack:
                    entries = await client.xreadgroup(
                        groupname=GROUP_NAME,
                        consumername=CONSUMER_NAME,
                        streams={STREAM_NAME: ">"},
                        count=100,
                        block=200,
                    )
                else:
                    # Use a simple last-id cursor stored in the store object
                    last_id = getattr(store, "_redis_last_id", "0-0")
                    entries = await client.xread(
                        streams={STREAM_NAME: last_id},
                        count=100,
                        block=200,
                    )

                if not entries:
                    continue

                for _stream_name, messages in entries:
                    for msg_id, fields in messages:
                        try:
                            data = json.loads(fields["data"])
                            msg = MessagePayload(**data)
                            store.record(msg.send_ts, msg.seq, acked=use_ack)

                            if use_ack:
                                await client.xack(STREAM_NAME, GROUP_NAME, msg_id)
                            else:
                                store._redis_last_id = msg_id
                        except Exception:
                            store.record_error()

            except aioredis.ResponseError:
                store.record_error()
                await asyncio.sleep(0.1)

    finally:
        await client.aclose()
