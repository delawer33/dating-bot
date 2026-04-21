import asyncio
import json
import os

import aio_pika

from metrics_store import MetricsStore
from models import BrokerConfig, MessagePayload

RMQ_URL = os.getenv("RMQ_URL", "amqp://guest:guest@localhost:5672/")
RMQ_QUEUE_DURABLE = "benchmark_queue_durable_ack"
RMQ_QUEUE_TRANSIENT = "benchmark_queue_inmemory_noack"


def _rmq_queue_name(cfg: BrokerConfig) -> str:
    return RMQ_QUEUE_DURABLE if cfg == BrokerConfig.durable_ack else RMQ_QUEUE_TRANSIENT


async def prepare_queue(config: BrokerConfig) -> None:
    """
    Declare the benchmark queue on the broker before returning from POST /start.

    This guarantees the queue exists (same args as the long-lived consumer task)
    before the runner starts the producer, so publishes are never unroutable.
    """
    connection = await aio_pika.connect_robust(RMQ_URL)
    try:
        channel = await connection.channel()
        qname = _rmq_queue_name(config)
        if config == BrokerConfig.durable_ack:
            await channel.declare_queue(qname, durable=True)
        else:
            await channel.declare_queue(qname, durable=False, auto_delete=False)
    finally:
        await connection.close()


async def run(config: BrokerConfig, store: MetricsStore, stop_event: asyncio.Event) -> None:
    use_ack = config == BrokerConfig.durable_ack

    connection = await aio_pika.connect_robust(RMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=100)

        qname = _rmq_queue_name(config)
        if use_ack:
            queue = await channel.declare_queue(qname, durable=True)
        else:
            queue = await channel.declare_queue(qname, durable=False, auto_delete=False)

        async with queue.iterator() as q_iter:
            async for message in q_iter:
                if stop_event.is_set():
                    await q_iter.close()
                    break

                try:
                    data = json.loads(message.body.decode())
                    msg = MessagePayload(**data)
                    store.record(msg.send_ts, msg.seq, acked=use_ack)
                    await message.ack()
                except Exception:
                    store.record_error()
                    try:
                        await message.nack(requeue=False)
                    except Exception:
                        pass
