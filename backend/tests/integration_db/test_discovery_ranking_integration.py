"""Real SQL for rank_candidate_ids (gender, distance, prior interactions)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.discovery import ranking as rk
from uuid import uuid4

from shared.db.models import Profile, ProfileInteraction, UserPreferences
from tests.factories.users import insert_user_with_profile

pytestmark = pytest.mark.integration_db


@pytest.mark.asyncio
async def test_rank_excludes_wrong_gender(db_session: AsyncSession) -> None:
    viewer = await insert_user_with_profile(
        db_session,
        telegram_id=70001,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["female"],
    )
    await insert_user_with_profile(
        db_session,
        telegram_id=70002,
        gender="male",
        birth_date=date(1994, 1, 1),
        combined_rating=99.0,
    )
    prefs = await db_session.get(UserPreferences, viewer.id)
    assert prefs is not None
    prof = await db_session.get(Profile, viewer.id)
    ids = await rk.rank_candidate_ids(db_session, viewer.id, prefs, prof)
    assert ids == []


@pytest.mark.asyncio
async def test_rank_excludes_already_seen(db_session: AsyncSession) -> None:
    viewer = await insert_user_with_profile(
        db_session,
        telegram_id=70010,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["female", "male"],
    )
    other = await insert_user_with_profile(
        db_session,
        telegram_id=70011,
        gender="female",
        birth_date=date(1993, 1, 1),
        combined_rating=10.0,
    )
    db_session.add(
        ProfileInteraction(
            id=uuid4(),
            actor_user_id=viewer.id,
            target_user_id=other.id,
            action="skip",
        )
    )
    await db_session.commit()

    prefs = await db_session.get(UserPreferences, viewer.id)
    prof = await db_session.get(Profile, viewer.id)
    ids = await rk.rank_candidate_ids(db_session, viewer.id, prefs, prof)
    assert other.id not in ids


@pytest.mark.asyncio
async def test_rank_distance_filters_far_candidates(db_session: AsyncSession) -> None:
    """Higher-rated but distant user is dropped when max_distance_km applies."""
    viewer = await insert_user_with_profile(
        db_session,
        telegram_id=70020,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["female"],
        max_distance_km=5,
        latitude=52.52,
        longitude=13.405,
    )
    near = await insert_user_with_profile(
        db_session,
        telegram_id=70021,
        display_name="Near",
        gender="female",
        birth_date=date(1995, 1, 1),
        combined_rating=1.0,
        latitude=52.521,
        longitude=13.405,
    )
    far = await insert_user_with_profile(
        db_session,
        telegram_id=70022,
        display_name="Far",
        gender="female",
        birth_date=date(1995, 2, 1),
        combined_rating=100.0,
        latitude=52.60,
        longitude=13.405,
    )

    prefs = await db_session.get(UserPreferences, viewer.id)
    prof = await db_session.get(Profile, viewer.id)
    ids = await rk.rank_candidate_ids(db_session, viewer.id, prefs, prof)
    assert near.id in ids
    assert far.id not in ids
