"""Redis discovery queue refill + pop against real Postgres."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.discovery import queue as dq
from shared.db.models import User, UserPreferences
from tests.factories.users import insert_user_with_profile

pytestmark = pytest.mark.integration_db


@pytest.mark.asyncio
async def test_pop_next_target_id_refills_queue(
    db_session: AsyncSession,
    redis_client,
) -> None:
    viewer = await insert_user_with_profile(
        db_session,
        telegram_id=70100,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["female"],
    )
    cand = await insert_user_with_profile(
        db_session,
        telegram_id=70101,
        gender="female",
        birth_date=date(1994, 1, 1),
        combined_rating=5.0,
    )

    prefs = await db_session.get(UserPreferences, viewer.id)
    assert prefs is not None
    user = await db_session.get(User, viewer.id)
    assert user is not None

    tid = await dq.pop_next_target_id(redis_client, db_session, user, prefs)
    assert tid == cand.id
