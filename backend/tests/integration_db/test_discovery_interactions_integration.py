"""Like/skip persistence and mutual match against Postgres + Redis."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.discovery import interactions as intr
from shared.db.models import Match, ProfileInteraction
from tests.factories.users import insert_user_with_profile

pytestmark = pytest.mark.integration_db


@pytest.mark.asyncio
async def test_record_like_then_reciprocal_creates_match(
    db_session: AsyncSession,
    redis_client,
    noop_publisher,
) -> None:
    a = await insert_user_with_profile(
        db_session,
        telegram_id=70200,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["male"],
    )
    b = await insert_user_with_profile(
        db_session,
        telegram_id=70201,
        gender="male",
        birth_date=date(1994, 1, 1),
        gender_preferences=["female"],
    )

    out1 = await intr.record_like(
        redis_client,
        db_session,
        noop_publisher,
        telegram_id=a.telegram_id,
        target_user_id=b.id,
    )
    assert out1["matched"] is False

    out2 = await intr.record_like(
        redis_client,
        db_session,
        noop_publisher,
        telegram_id=b.telegram_id,
        target_user_id=a.id,
    )
    assert out2["matched"] is True
    assert out2["match_id"] is not None

    ua, ub = (a.id, b.id) if a.id < b.id else (b.id, a.id)
    m = await db_session.scalar(select(Match.id).where(Match.user_a_id == ua, Match.user_b_id == ub))
    assert m is not None


@pytest.mark.asyncio
async def test_record_like_duplicate_returns_409(
    db_session: AsyncSession,
    redis_client,
    noop_publisher,
) -> None:
    a = await insert_user_with_profile(
        db_session,
        telegram_id=70210,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["male"],
    )
    b = await insert_user_with_profile(
        db_session,
        telegram_id=70211,
        gender="male",
        birth_date=date(1994, 1, 1),
        gender_preferences=["female"],
    )
    await intr.record_like(
        redis_client,
        db_session,
        noop_publisher,
        telegram_id=a.telegram_id,
        target_user_id=b.id,
    )
    with pytest.raises(HTTPException) as exc:
        await intr.record_like(
            redis_client,
            db_session,
            noop_publisher,
            telegram_id=a.telegram_id,
            target_user_id=b.id,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_record_skip_persists(
    db_session: AsyncSession,
    redis_client,
    noop_publisher,
) -> None:
    a = await insert_user_with_profile(
        db_session,
        telegram_id=70220,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["male"],
    )
    b = await insert_user_with_profile(
        db_session,
        telegram_id=70221,
        gender="male",
        birth_date=date(1994, 1, 1),
        gender_preferences=["female"],
    )
    await intr.record_skip(
        redis_client,
        db_session,
        noop_publisher,
        telegram_id=a.telegram_id,
        target_user_id=b.id,
    )
    row = await db_session.scalar(
        select(ProfileInteraction.id).where(
            ProfileInteraction.actor_user_id == a.id,
            ProfileInteraction.target_user_id == b.id,
            ProfileInteraction.action == "skip",
        )
    )
    assert row is not None
