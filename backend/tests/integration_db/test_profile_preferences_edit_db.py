"""profile_edit_service and preferences_edit_service against Postgres."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import preferences_edit_service as prefs
from api.services import profile_edit_service as pe
from shared.db.models import ProfilePhoto
from shared.geo.provider import GeoLocation
from tests.factories.users import insert_user_with_profile

pytestmark = pytest.mark.integration_db


@pytest.mark.asyncio
async def test_profile_edit_display_birth_gender_bio_interests(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92001,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    await pe.edit_display_name(db_session, u.telegram_id, "NewName")
    await pe.edit_birth_date(db_session, u.telegram_id, date(1994, 6, 6))
    await pe.edit_gender(db_session, u.telegram_id, "male")
    redis = AsyncMock()
    geo = AsyncMock()
    geo.reverse_geocode = AsyncMock(return_value=GeoLocation(city="Bergen", district="Centrum"))
    await pe.edit_location(db_session, redis, u.telegram_id, 60.4, 5.3, geo)
    await pe.edit_bio(db_session, u.telegram_id, "Bio text")
    await pe.edit_interests(db_session, u.telegram_id, ["music", "books"])


@pytest.mark.asyncio
async def test_profile_edit_bio_too_long(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92002,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    with pytest.raises(HTTPException) as ei:
        await pe.edit_bio(db_session, u.telegram_id, "x" * 5000)
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_profile_edit_interests_too_many_and_unknown(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92003,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    with pytest.raises(HTTPException):
        await pe.edit_interests(db_session, u.telegram_id, ["music"] * 20)
    with pytest.raises(HTTPException):
        await pe.edit_interests(db_session, u.telegram_id, ["not-a-real-id"])


@pytest.mark.asyncio
async def test_profile_edit_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as ei:
        await pe.edit_display_name(db_session, 999_999_999, "X")
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_profile_edit_before_registration_done(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92004,
        gender="female",
        birth_date=date(1995, 5, 5),
        registration_completed=False,
    )
    with pytest.raises(HTTPException) as ei:
        await pe.edit_display_name(db_session, u.telegram_id, "X")
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_profile_edit_geocode_error(db_session: AsyncSession) -> None:
    from shared.geo.provider import GeocodingError

    u = await insert_user_with_profile(
        db_session,
        telegram_id=92005,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    redis = AsyncMock()
    geo = AsyncMock()
    geo.reverse_geocode = AsyncMock(side_effect=GeocodingError("fail"))
    with pytest.raises(HTTPException) as ei:
        await pe.edit_location(db_session, redis, u.telegram_id, 1.0, 1.0, geo)
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_profile_delete_and_reorder_photos(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92006,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    db_session.add_all(
        [
            ProfilePhoto(
                id=p1,
                profile_id=u.id,
                s3_key=f"profiles/{u.id}/a.jpg",
                telegram_file_id="a",
                sort_order=1,
            ),
            ProfilePhoto(
                id=p2,
                profile_id=u.id,
                s3_key=f"profiles/{u.id}/b.jpg",
                telegram_file_id="b",
                sort_order=2,
            ),
        ]
    )
    await db_session.commit()
    s3 = MagicMock()
    await pe.delete_profile_photo(db_session, s3, u.telegram_id, p2)
    await pe.reorder_profile_photos(db_session, u.telegram_id, [p1])


@pytest.mark.asyncio
async def test_profile_delete_photo_not_found_and_min_photos(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92007,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    db_session.add(
        ProfilePhoto(
            id=uuid.uuid4(),
            profile_id=u.id,
            s3_key=f"profiles/{u.id}/only.jpg",
            telegram_file_id="a",
            sort_order=1,
        )
    )
    await db_session.commit()
    s3 = MagicMock()
    with pytest.raises(HTTPException) as ei:
        await pe.delete_profile_photo(db_session, s3, u.telegram_id, uuid.uuid4())
    assert ei.value.status_code == 404
    only_id = await db_session.scalar(select(ProfilePhoto.id).where(ProfilePhoto.profile_id == u.id))
    assert only_id is not None
    with pytest.raises(HTTPException) as ei2:
        await pe.delete_profile_photo(db_session, s3, u.telegram_id, only_id)
    assert ei2.value.status_code == 422


@pytest.mark.asyncio
async def test_profile_reorder_invalid_ids(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92008,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    pid = uuid.uuid4()
    db_session.add(
        ProfilePhoto(
            id=pid,
            profile_id=u.id,
            s3_key=f"profiles/{u.id}/a.jpg",
            telegram_file_id="a",
            sort_order=1,
        )
    )
    await db_session.commit()
    with pytest.raises(HTTPException):
        await pe.reorder_profile_photos(db_session, u.telegram_id, [pid, uuid.uuid4()])


@pytest.mark.asyncio
async def test_preferences_edit_and_errors(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92009,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    await prefs.edit_age_range(db_session, u.telegram_id, 21, 55)
    await prefs.edit_gender_preferences(db_session, u.telegram_id, ["female"])
    await prefs.edit_max_distance(db_session, u.telegram_id, 100)


@pytest.mark.asyncio
async def test_preferences_not_done_forbidden(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92010,
        gender="female",
        birth_date=date(1995, 5, 5),
        registration_completed=False,
    )
    with pytest.raises(HTTPException) as ei:
        await prefs.edit_age_range(db_session, u.telegram_id, 18, 30)
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_preferences_age_validation(db_session: AsyncSession) -> None:
    u = await insert_user_with_profile(
        db_session,
        telegram_id=92011,
        gender="female",
        birth_date=date(1995, 5, 5),
    )
    with pytest.raises(HTTPException):
        await prefs.edit_age_range(db_session, u.telegram_id, 40, 20)


@pytest.mark.asyncio
async def test_preferences_user_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as ei:
        await prefs.edit_max_distance(db_session, 888_888_888, 10)
    assert ei.value.status_code == 404
