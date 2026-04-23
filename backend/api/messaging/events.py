"""Publish profile interaction events to the `dating.events` topic exchange."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika
from aio_pika import ExchangeType, Message

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "dating.events"


class EventPublisher:
    """Async publisher; connect once at app lifespan."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: aio_pika.RobustConnection | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        channel = await self._connection.channel()
        self._exchange = await channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._exchange = None

    async def publish(self, routing_key: str, event_type: str, payload: dict[str, Any]) -> None:
        if self._exchange is None:
            raise RuntimeError("EventPublisher not connected")
        envelope = {
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": 1,
            "payload": payload,
        }
        body = json.dumps(envelope, default=str).encode("utf-8")
        msg = Message(body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
        await self._exchange.publish(msg, routing_key=routing_key)
        logger.debug("Published %s rk=%s", event_type, routing_key)

    async def publish_profile_liked(
        self,
        *,
        actor_user_id: uuid.UUID,
        target_user_id: uuid.UUID,
        interaction_id: uuid.UUID,
        creates_match: bool = False,
    ) -> None:
        await self.publish(
            "profile.liked",
            "profile.liked",
            {
                "actor_user_id": str(actor_user_id),
                "target_user_id": str(target_user_id),
                "interaction_id": str(interaction_id),
                "creates_match": creates_match,
            },
        )

    async def publish_profile_skipped(
        self,
        *,
        actor_user_id: uuid.UUID,
        target_user_id: uuid.UUID,
        interaction_id: uuid.UUID,
    ) -> None:
        await self.publish(
            "profile.skipped",
            "profile.skipped",
            {
                "actor_user_id": str(actor_user_id),
                "target_user_id": str(target_user_id),
                "interaction_id": str(interaction_id),
            },
        )

    async def publish_match_created(
        self,
        *,
        match_id: uuid.UUID,
        user_a_id: uuid.UUID,
        user_b_id: uuid.UUID,
        initiated_by_user_id: uuid.UUID,
    ) -> None:
        await self.publish(
            "match.created",
            "match.created",
            {
                "match_id": str(match_id),
                "user_a_id": str(user_a_id),
                "user_b_id": str(user_b_id),
                "initiated_by_user_id": str(initiated_by_user_id),
            },
        )
