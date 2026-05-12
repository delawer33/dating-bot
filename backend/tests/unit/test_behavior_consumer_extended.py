"""More branches on workers.behavior_consumer."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workers import behavior_consumer as bc


def test_histogram_bucket_naive_datetime_gets_utc() -> None:
    b = bc._histogram_bucket("2026-05-11T12:00:00")
    assert b is not None


@pytest.mark.asyncio
async def test_apply_event_match_created() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    envelope = {
        "type": "match.created",
        "payload": {"user_a_id": str(a), "user_b_id": str(b)},
        "occurred_at": "2026-05-11T12:00:00Z",
    }
    row_a = MagicMock()
    row_a.matches_count = 0
    row_a.likes_received = 0
    row_a.skips_received = 0
    row_b = MagicMock()
    row_b.matches_count = 0
    row_b.likes_received = 0
    row_b.skips_received = 0
    session = AsyncMock()

    async def _get(_model, pk):
        return row_a if pk == a else row_b

    session.get = AsyncMock(side_effect=_get)

    out = await bc._apply_event(session, envelope)
    assert set(out) == {a, b}
    assert row_a.matches_count == 1
    assert row_b.matches_count == 1


@pytest.mark.asyncio
async def test_apply_event_unknown_type() -> None:
    session = AsyncMock()
    out = await bc._apply_event(session, {"type": "other", "payload": {}, "occurred_at": ""})
    assert out == []


@pytest.mark.asyncio
async def test_handle_delivery_missing_event_id_returns() -> None:
    body = json.dumps({"type": "profile.liked"}).encode()
    redis = AsyncMock()
    factory = MagicMock()
    await bc._handle_delivery(body, redis, factory)
    redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_handle_delivery_match_created_notifies() -> None:
    uid = uuid.uuid4()
    eid = str(uuid.uuid4())
    body = json.dumps(
        {
            "event_id": eid,
            "type": "match.created",
            "payload": {"user_a_id": str(uid), "user_b_id": str(uuid.uuid4())},
            "occurred_at": "2026-05-11T12:00:00Z",
        }
    ).encode()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    session = AsyncMock()

    @asynccontextmanager
    async def _begin() -> None:
        yield

    session.begin = MagicMock(return_value=_begin())

    @asynccontextmanager
    async def _sess():
        yield session

    mgr1, mgr2 = _sess(), _sess()
    factory = MagicMock(side_effect=[mgr1, mgr2])
    with patch.object(bc, "_apply_event", new_callable=AsyncMock, return_value=[uid]):
        with patch.object(bc, "send_telegram_for_event", new_callable=AsyncMock) as notify:
            with patch.object(bc.celery_app, "send_task"):
                await bc._handle_delivery(body, redis, factory)
    notify.assert_awaited()


@pytest.mark.asyncio
async def test_handle_delivery_notify_failure_swallowed() -> None:
    uid = uuid.uuid4()
    eid = str(uuid.uuid4())
    body = json.dumps(
        {
            "event_id": eid,
            "type": "match.created",
            "payload": {"user_a_id": str(uid), "user_b_id": str(uuid.uuid4())},
        }
    ).encode()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    session = AsyncMock()

    @asynccontextmanager
    async def _begin() -> None:
        yield

    session.begin = MagicMock(return_value=_begin())

    @asynccontextmanager
    async def _sess():
        yield session

    m1, m2 = _sess(), _sess()
    factory = MagicMock(side_effect=[m1, m2])
    with patch.object(bc, "_apply_event", new_callable=AsyncMock, return_value=[uid]):
        with patch.object(bc, "send_telegram_for_event", new_callable=AsyncMock, side_effect=RuntimeError("tg")):
            with patch.object(bc.celery_app, "send_task"):
                await bc._handle_delivery(body, redis, factory)


@pytest.mark.asyncio
async def test_handle_delivery_celery_failure_swallowed() -> None:
    uid = uuid.uuid4()
    eid = str(uuid.uuid4())
    body = json.dumps(
        {
            "event_id": eid,
            "type": "profile.skipped",
            "payload": {"target_user_id": str(uid)},
            "occurred_at": "2026-05-11T12:00:00Z",
        }
    ).encode()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    session = AsyncMock()

    @asynccontextmanager
    async def _begin() -> None:
        yield

    session.begin = MagicMock(return_value=_begin())

    @asynccontextmanager
    async def _sess():
        yield session

    factory = MagicMock(side_effect=[_sess()])
    with patch.object(bc, "_apply_event", new_callable=AsyncMock, return_value=[uid]):
        with patch.object(bc.celery_app, "send_task", side_effect=RuntimeError("celery")):
            await bc._handle_delivery(body, redis, factory)
