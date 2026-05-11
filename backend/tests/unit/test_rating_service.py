"""Rating persistence — mocked async session."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services import rating_service
from shared.db.models import Profile, User, UserBehaviorStats, UserPreferences, UserRating


@pytest.mark.asyncio
async def test_recompute_user_rating_upserts_row() -> None:
    uid = uuid.uuid4()
    user = MagicMock(spec=User)
    profile = MagicMock(spec=Profile)
    profile.completeness_score = 60
    prefs = MagicMock(spec=UserPreferences)
    prefs.max_distance_km = 25
    stats = MagicMock(spec=UserBehaviorStats)
    stats.likes_received = 3
    stats.skips_received = 1
    stats.matches_count = 0

    rating_row = MagicMock(spec=UserRating)
    rating_row.combined_score = 0.42

    fetch_result = MagicMock()
    fetch_result.one_or_none = MagicMock(return_value=(user, profile, prefs, stats, 0))

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[fetch_result, MagicMock()])
    session.get = AsyncMock(return_value=rating_row)
    session.flush = AsyncMock()

    out = await rating_service.recompute_user_rating(session, uid)
    assert out is rating_row
    assert session.execute.await_count == 2
    session.get.assert_awaited_once_with(UserRating, uid)
