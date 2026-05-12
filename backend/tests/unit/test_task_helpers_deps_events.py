"""api.services.task_helpers, api.dependencies edges, EventPublisher."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.dependencies import get_event_publisher, get_redis, require_bot_auth
from api.messaging.events import EventPublisher


def test_schedule_rating_recompute_success() -> None:
    uid = uuid.uuid4()
    with patch("workers.celery_app.celery_app") as app:
        from api.services import task_helpers

        task_helpers.schedule_rating_recompute(uid)
    app.send_task.assert_called_once_with("rating.recompute_user", args=[str(uid)])


def test_schedule_rating_recompute_swallows_exception() -> None:
    uid = uuid.uuid4()
    with patch("workers.celery_app.celery_app") as app:
        app.send_task.side_effect = RuntimeError("broker down")
        from api.services import task_helpers

        task_helpers.schedule_rating_recompute(uid)


@pytest.mark.asyncio
async def test_require_bot_auth_rejects() -> None:
    with pytest.raises(HTTPException) as ei:
        await require_bot_auth(None)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_get_event_publisher_missing_returns_503() -> None:
    req = MagicMock()
    req.app.state = MagicMock(event_publisher=None)
    with pytest.raises(HTTPException) as ei:
        get_event_publisher(req)
    assert ei.value.status_code == 503


def test_get_redis_raises_when_uninitialised() -> None:
    import api.dependencies as dep

    with patch.object(dep, "_redis_client", None):
        with pytest.raises(RuntimeError, match="Redis not initialised"):
            dep.get_redis()


@pytest.mark.asyncio
async def test_event_publisher_publish_and_close() -> None:
    pub = EventPublisher("amqp://x")
    ch = AsyncMock()
    ch.declare_exchange = AsyncMock()
    conn = AsyncMock()
    conn.channel = AsyncMock(return_value=ch)
    conn.close = AsyncMock()
    with patch("api.messaging.events.aio_pika.connect_robust", new_callable=AsyncMock, return_value=conn):
        await pub.connect()
    ex = ch.declare_exchange.return_value
    ex.publish = AsyncMock()
    await pub.publish("rk", "t", {"a": 1})
    ex.publish.assert_awaited()
    await pub.close()
    conn.close.assert_awaited()


@pytest.mark.asyncio
async def test_event_publish_not_connected_raises() -> None:
    pub = EventPublisher("amqp://x")
    with pytest.raises(RuntimeError, match="not connected"):
        await pub.publish("k", "t", {})
