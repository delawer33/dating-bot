"""workers.notification_hooks — Telegram side effects mocked."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from shared.db.models import Profile, User
from workers.notification_hooks import send_telegram_for_event


@pytest.mark.asyncio
async def test_send_telegram_for_event_unknown_type() -> None:
    session = AsyncMock()
    await send_telegram_for_event(session, {"type": "other", "payload": {}})
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_profile_liked_skips_when_creates_match() -> None:
    session = AsyncMock()
    await send_telegram_for_event(
        session,
        {"type": "profile.liked", "payload": {"creates_match": True}},
    )
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_profile_liked_bad_payload_logs() -> None:
    session = AsyncMock()
    await send_telegram_for_event(session, {"type": "profile.liked", "payload": {}})
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_profile_liked_no_target_telegram() -> None:
    tid = uuid.uuid4()
    aid = uuid.uuid4()
    target = User(id=tid, telegram_id=None, username=None, registration_completed=True)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[target, None])
    with patch("workers.notification_hooks.send_telegram_text", new_callable=AsyncMock) as send:
        await send_telegram_for_event(
            session,
            {
                "type": "profile.liked",
                "payload": {
                    "target_user_id": str(tid),
                    "actor_user_id": str(aid),
                    "creates_match": False,
                },
            },
        )
    send.assert_not_called()


@pytest.mark.asyncio
async def test_profile_liked_sends_message() -> None:
    tid = uuid.uuid4()
    aid = uuid.uuid4()
    target = User(id=tid, telegram_id=555001, username=None, registration_completed=True)
    actor_prof = Profile(user_id=aid, display_name="Alex")
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[target, actor_prof])
    with patch("workers.notification_hooks.send_telegram_text", new_callable=AsyncMock) as send:
        await send_telegram_for_event(
            session,
            {
                "type": "profile.liked",
                "payload": {
                    "target_user_id": str(tid),
                    "actor_user_id": str(aid),
                    "creates_match": False,
                },
            },
        )
    assert send.await_args[0][0] == 555001
    assert "лайкнул" in send.await_args[0][1]


@pytest.mark.asyncio
async def test_match_created_both_when_no_initiator() -> None:
    ua, ub = uuid.uuid4(), uuid.uuid4()
    user_a = User(id=ua, telegram_id=1, username=None, registration_completed=True)
    user_b = User(id=ub, telegram_id=2, username=None, registration_completed=True)
    prof_a = Profile(user_id=ua, display_name="A")
    prof_b = Profile(user_id=ub, display_name="B")
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[user_a, user_b, prof_a, prof_b])
    with patch("workers.notification_hooks.send_telegram_text", new_callable=AsyncMock) as send:
        await send_telegram_for_event(
            session,
            {"type": "match.created", "payload": {"user_a_id": str(ua), "user_b_id": str(ub)}},
        )
    assert send.await_count == 2


@pytest.mark.asyncio
async def test_match_created_initiator_a_only_b() -> None:
    ua, ub = uuid.uuid4(), uuid.uuid4()
    user_a = User(id=ua, telegram_id=1, username=None, registration_completed=True)
    user_b = User(id=ub, telegram_id=2, username=None, registration_completed=True)
    prof_a = Profile(user_id=ua, display_name="A")
    prof_b = Profile(user_id=ub, display_name="B")
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[user_a, user_b, prof_a, prof_b])
    with patch("workers.notification_hooks.send_telegram_text", new_callable=AsyncMock) as send:
        await send_telegram_for_event(
            session,
            {
                "type": "match.created",
                "payload": {
                    "user_a_id": str(ua),
                    "user_b_id": str(ub),
                    "initiated_by_user_id": str(ua),
                },
            },
        )
    assert send.await_count == 1
    assert send.await_args[0][0] == 2


@pytest.mark.asyncio
async def test_match_created_bad_payload() -> None:
    session = AsyncMock()
    await send_telegram_for_event(session, {"type": "match.created", "payload": {}})
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_match_created_invalid_initiator_ignored() -> None:
    ua, ub = uuid.uuid4(), uuid.uuid4()
    user_a = User(id=ua, telegram_id=1, username=None, registration_completed=True)
    user_b = User(id=ub, telegram_id=2, username=None, registration_completed=True)
    prof_a = Profile(user_id=ua, display_name="A")
    prof_b = Profile(user_id=ub, display_name="B")
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[user_a, user_b, prof_a, prof_b])
    with patch("workers.notification_hooks.send_telegram_text", new_callable=AsyncMock) as send:
        await send_telegram_for_event(
            session,
            {
                "type": "match.created",
                "payload": {
                    "user_a_id": str(ua),
                    "user_b_id": str(ub),
                    "initiated_by_user_id": "not-a-uuid",
                },
            },
        )
    assert send.await_count == 2
