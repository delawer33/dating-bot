import asyncio
import base64
import json
import os
import time
import uuid

import aio_pika

from models import BrokerConfig, MessagePayload, RunConfig
from rate_limiter import TokenBucketRateLimiter

RMQ_URL = os.getenv("RMQ_URL", "amqp://guest:guest@localhost:5672/")

# Separate names per config — RabbitMQ rejects redeclare with different durability.
RMQ_QUEUE_DURABLE = "benchmark_queue_durable_ack"
RMQ_QUEUE_TRANSIENT = "benchmark_queue_inmemory_noack"


def _rmq_queue_name(cfg: BrokerConfig) -> str:
    return RMQ_QUEUE_DURABLE if cfg == BrokerConfig.durable_ack else RMQ_QUEUE_TRANSIENT


async def run(config: RunConfig, stop_event: asyncio.Event, sent_counter: list[int]) -> None:
    use_confirms = config.config == BrokerConfig.durable_ack
    connection = await aio_pika.connect_robust(RMQ_URL)
    async with connection:
        channel = await connection.channel(publisher_confirms=use_confirms)

        qname = _rmq_queue_name(config.config)
        if config.config == BrokerConfig.durable_ack:
            queue = await channel.declare_queue(qname, durable=True)
            delivery_mode = aio_pika.DeliveryMode.PERSISTENT
        else:
            # Non-durable, not auto_delete: auto_delete races with /start returning
            # before the consumer task has registered; flush deletes this queue.
            queue = await channel.declare_queue(qname, durable=False, auto_delete=False)
            delivery_mode = aio_pika.DeliveryMode.NOT_PERSISTENT

        # Pre-build a payload of exactly msg_size bytes
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
            body = json.dumps(msg.model_dump()).encode()

            amqp_msg = aio_pika.Message(
                body=body,
                delivery_mode=delivery_mode,
            )

            try:
                await channel.default_exchange.publish(
                    amqp_msg,
                    routing_key=queue.name,
                )
                sent_counter[0] += 1
                seq += 1
            except Exception:
                pass


async def flush_queue() -> None:
    """Remove benchmark queues so the next run starts clean."""
    connection = await aio_pika.connect_robust(RMQ_URL)
    async with connection:
        channel = await connection.channel()
        for name in (RMQ_QUEUE_DURABLE, RMQ_QUEUE_TRANSIENT):
            try:
                q = await channel.declare_queue(name, passive=True)
                await q.delete(if_unused=False, if_empty=False)
            except Exception:
                pass
