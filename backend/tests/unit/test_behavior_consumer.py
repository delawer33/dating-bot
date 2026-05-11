"""Behavior consumer helpers and delivery path (mocked I/O)."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workers import behavior_consumer as bc


def test_histogram_bucket_parses_iso() -> None:
    b = bc._histogram_bucket("2026-05-11T15:30:00Z")
    assert b is not None
    assert 0 <= b < 7 * 24


def test_histogram_bucket_invalid() -> None:
    assert bc._histogram_bucket("not-a-date") is None


def test_merge_bucket_updates_histogram() -> None:
    row = MagicMock()
    row.activity_histogram = None
    bc._merge_bucket(row, 10)
    assert row.activity_histogram is not None
    assert row.activity_histogram.get("10") == 1
    bc._merge_bucket(row, 10)
    assert row.activity_histogram["10"] == 2


@pytest.mark.asyncio
async def test_apply_event_profile_liked() -> None:
    target_id = uuid.uuid4()
    envelope = {
        "type": "profile.liked",
        "payload": {"target_user_id": str(target_id)},
        "occurred_at": "2026-05-11T12:00:00Z",
    }
    row = MagicMock()
    row.likes_received = 0
    row.skips_received = 0
    row.matches_count = 0
    session = AsyncMock()
    session.get = AsyncMock(return_value=row)

    affected = await bc._apply_event(session, envelope)
    assert affected == [target_id]
    assert row.likes_received == 1


@pytest.mark.asyncio
async def test_handle_delivery_dedup_skips_apply() -> None:
    eid = str(uuid.uuid4())
    body = json.dumps(
        {"event_id": eid, "type": "profile.liked", "payload": {"target_user_id": str(uuid.uuid4())}}
    ).encode()

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=False)

    @asynccontextmanager
    async def _sess():
        yield AsyncMock()

    factory = MagicMock(return_value=_sess())

    with patch.object(bc, "_apply_event", new_callable=AsyncMock) as apply_m:
        await bc._handle_delivery(body, redis, factory)
    apply_m.assert_not_called()


@pytest.mark.asyncio
async def test_handle_delivery_enqueues_rating() -> None:
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

    factory = MagicMock(return_value=_sess())

    with patch.object(bc, "_apply_event", new_callable=AsyncMock, return_value=[uid]):
        with patch.object(bc, "send_telegram_for_event", new_callable=AsyncMock):
            with patch.object(bc.celery_app, "send_task") as send_task:
                await bc._handle_delivery(body, redis, factory)
    send_task.assert_called_once_with("rating.recompute_user", args=[str(uid)])
