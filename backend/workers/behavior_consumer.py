"""Consume `behavior.aggregate` and update `user_behavior_stats`, then enqueue rating jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
import redis.asyncio as aioredis
from aio_pika import ExchangeType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.messaging.events import EXCHANGE_NAME
from shared.db.models import UserBehaviorStats
from workers.celery_app import celery_app
from workers.db import create_async_engine_and_sessionmaker
from workers.notification_hooks import send_telegram_for_event

logger = logging.getLogger(__name__)

QUEUE_NAME = "behavior.aggregate"


def _histogram_bucket(occurred_at: str) -> int | None:
    try:
        raw = occurred_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.weekday() * 24 + dt.hour
    except (TypeError, ValueError, OSError):
        return None


def _merge_bucket(row: UserBehaviorStats, bucket: int | None) -> None:
    if bucket is None:
        return
    hist = dict(row.activity_histogram or {})
    key = str(bucket)
    hist[key] = int(hist.get(key, 0)) + 1
    row.activity_histogram = hist


async def _ensure_stats_row(session: AsyncSession, user_id: uuid.UUID) -> UserBehaviorStats:
    row = await session.get(UserBehaviorStats, user_id)
    if row is None:
        row = UserBehaviorStats(
            user_id=user_id,
            likes_received=0,
            skips_received=0,
            matches_count=0,
        )
        session.add(row)
        await session.flush()
    return row


async def _apply_event(session: AsyncSession, envelope: dict[str, Any]) -> list[uuid.UUID]:
    etype = envelope["type"]
    payload = envelope["payload"]
    occurred_at = str(envelope.get("occurred_at", ""))
    bucket = _histogram_bucket(occurred_at)
    affected: list[uuid.UUID] = []
    now = datetime.now(timezone.utc)

    if etype == "profile.liked":
        target_id = uuid.UUID(payload["target_user_id"])
        row = await _ensure_stats_row(session, target_id)
        row.likes_received += 1
        row.updated_at = now
        _merge_bucket(row, bucket)
        affected.append(target_id)
    elif etype == "profile.skipped":
        target_id = uuid.UUID(payload["target_user_id"])
        row = await _ensure_stats_row(session, target_id)
        row.skips_received += 1
        row.updated_at = now
        _merge_bucket(row, bucket)
        affected.append(target_id)
    elif etype == "match.created":
        a = uuid.UUID(payload["user_a_id"])
        b = uuid.UUID(payload["user_b_id"])
        for uid in (a, b):
            row = await _ensure_stats_row(session, uid)
            row.matches_count += 1
            row.updated_at = now
            _merge_bucket(row, bucket)
            affected.append(uid)
    else:
        logger.warning("Unknown event type: %s", etype)
    return affected


async def _handle_delivery(
    body: bytes,
    redis: aioredis.Redis,
    factory: async_sessionmaker,
) -> None:
    envelope = json.loads(body.decode("utf-8"))
    event_id = envelope.get("event_id")
    if not event_id:
        return
    if not await redis.set(f"events:dedup:{event_id}", "1", nx=True, ex=86400):
        logger.debug("Duplicate event %s skipped", event_id)
        return

    async with factory() as session:
        async with session.begin():
            affected = await _apply_event(session, envelope)

    etype = envelope.get("type")
    if etype in ("profile.liked", "match.created"):
        try:
            async with factory() as session:
                await send_telegram_for_event(session, envelope)
        except Exception:
            logger.exception("Telegram notification failed for %s", etype)

    for uid in affected:
        try:
            celery_app.send_task("rating.recompute_user", args=[str(uid)])
        except Exception:
            logger.exception("Failed to enqueue rating.recompute_user for %s", uid)


async def run_consumer() -> None:
    redis_url = os.environ["REDIS_URL"]
    amqp_url = os.environ.get("RABBITMQ_URL") or os.environ.get("CELERY_BROKER_URL")
    if not amqp_url:
        raise RuntimeError("RABBITMQ_URL or CELERY_BROKER_URL is required")

    redis = await aioredis.from_url(redis_url, decode_responses=True)
    _engine, factory = create_async_engine_and_sessionmaker()

    connection = await aio_pika.connect_robust(amqp_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    for key in ("profile.liked", "profile.skipped", "match.created"):
        await queue.bind(exchange, routing_key=key)

    logger.info("Behavior consumer listening on %s", QUEUE_NAME)

    async def on_message(message: AbstractIncomingMessage) -> None:
        async with message.process():
            try:
                await _handle_delivery(message.body, redis, factory)
            except Exception:
                logger.exception("Failed to process message")

    await queue.consume(on_message)
    await asyncio.Event().wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
