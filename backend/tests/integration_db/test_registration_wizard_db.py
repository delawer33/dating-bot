"""Walk registration_service through Postgres (geocoder + Telegram upload mocked)."""

from __future__ import annotations

from datetime import date
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import api.services.registration_service as rs
from shared.db.models import ProfilePhoto, User
from shared.geo.provider import GeoLocation

pytestmark = pytest.mark.integration_db


@pytest.mark.asyncio
async def test_registration_wizard_to_complete(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.services.task_helpers.schedule_rating_recompute", lambda *_a, **_k: None)
    tid = 910_000
    geo = AsyncMock()
    geo.reverse_geocode = AsyncMock(return_value=GeoLocation(city="Oslo", district=None))

    async def _fake_add_photo(session, user_id, profile, file_id, s3_client, **kwargs):
        db_session.add(
            ProfilePhoto(
                id=uuid.uuid4(),
                profile_id=user_id,
                s3_key=f"profiles/{user_id}/x.jpg",
                telegram_file_id=file_id,
                sort_order=1,
            )
        )
        await db_session.commit()
        await db_session.refresh(profile)
        return profile

    with patch.object(rs, "add_photo_from_telegram", new=AsyncMock(side_effect=_fake_add_photo)):
        u, is_new = await rs.registration_start(db_session, tid, "u1", None)
        assert is_new is True
        await rs.set_display_name(db_session, tid, "Wizard")
        await rs.set_birth_date(db_session, tid, date(2000, 1, 15))
        await rs.set_gender(db_session, tid, "female")
        await rs.set_location(db_session, tid, 59.9, 10.7, geo)
        s3 = MagicMock()
        await rs.add_registration_photo(db_session, tid, "tg-file-1", s3)
        await rs.set_registration_search_age(db_session, tid, 20, 40)
        await rs.set_registration_search_gender(db_session, tid, ["male"])
        await rs.set_registration_search_distance(db_session, tid, 50)
        await rs.set_registration_bio(db_session, tid, "Hi")
        await rs.set_registration_interests(db_session, tid, ["music"])
        user, prof, prefs = await rs.complete_registration(db_session, tid)

    assert user.registration_completed is True
    row = await db_session.scalar(select(User).where(User.telegram_id == tid))
    assert row is not None
    assert row.registration_completed is True
