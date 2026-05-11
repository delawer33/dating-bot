"""Profile card, profile/me, preferences, and profile edit services against Postgres."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import preferences_edit_service as pref_edit
from api.services import profile_edit_service as prof_edit
from api.services import profile_service as prof_svc
from api.services.photo_presign import StubPhotoPresigner
from api.services.profile_card import build_profile_card
from shared.db.models import ProfilePhoto, UserPreferences
from tests.factories.users import insert_user_with_profile

pytestmark = pytest.mark.integration_db


@pytest.mark.asyncio
async def test_build_profile_card_with_stub_presigner(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=70300,
        gender="female",
        birth_date=date(1995, 3, 3),
    )
    pid = uuid4()
    db_session.add(
        ProfilePhoto(
            id=pid,
            profile_id=u.id,
            s3_key="profiles/x/photo1.jpg",
            telegram_file_id="tg-file",
            sort_order=1,
        )
    )
    await db_session.commit()

    card = await build_profile_card(db_session, u.id, StubPhotoPresigner("https://signed.example/"))
    assert len(card["photos"]) == 1
    assert card["photos"][0]["presigned_url"] == "https://signed.example/profiles/x/photo1.jpg"


@pytest.mark.asyncio
async def test_get_profile_me_returns_preferences_and_step(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=70301,
        gender="female",
        birth_date=date(1995, 3, 3),
    )
    payload = await prof_svc.get_profile_me(db_session, u.telegram_id, None)
    assert payload["is_complete"] is True
    assert payload["preferences"] is not None
    assert payload["preferences"]["age_min"] == 18


@pytest.mark.asyncio
async def test_edit_age_range_persisted(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=70302,
        gender="female",
        birth_date=date(1995, 3, 3),
    )
    await pref_edit.edit_age_range(db_session, u.telegram_id, 22, 44)
    prefs = await db_session.get(UserPreferences, u.id)
    assert prefs is not None
    assert prefs.age_min == 22
    assert prefs.age_max == 44


@pytest.mark.asyncio
async def test_edit_display_name_persisted(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=70303,
        display_name="Old",
        gender="female",
        birth_date=date(1995, 3, 3),
    )
    prof = await prof_edit.edit_display_name(db_session, u.telegram_id, "NewName")
    assert prof.display_name == "NewName"


@pytest.mark.asyncio
async def test_count_profile_photos_via_photo_row(db_session: AsyncSession) -> None:
    from api.services.profile_photo_service import count_profile_photos

    u = await insert_user_with_profile(
        db_session,
        telegram_id=70304,
        gender="female",
        birth_date=date(1995, 3, 3),
    )
    db_session.add(
        ProfilePhoto(
            id=uuid4(),
            profile_id=u.id,
            s3_key="profiles/x/a.jpg",
            telegram_file_id="a",
            sort_order=1,
        )
    )
    await db_session.commit()
    n = await count_profile_photos(db_session, u.id)
    assert n == 1
