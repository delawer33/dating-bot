"""Insert minimal user + profile + preferences (+ optional rating) rows."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from shared.db.models import Profile, ProfilePhoto, User, UserPreferences, UserRating


async def insert_user_with_profile(
    session: AsyncSession,
    *,
    telegram_id: int,
    display_name: str = "User",
    birth_date: date | None = None,
    gender: str | None = "female",
    city: str | None = "Town",
    latitude: float | None = None,
    longitude: float | None = None,
    registration_completed: bool = True,
    age_min: int = 18,
    age_max: int = 99,
    gender_preferences: list[str] | None = None,
    max_distance_km: int | None = None,
    combined_rating: float | None = None,
) -> User:
    if birth_date is None:
        birth_date = date(1995, 6, 15)
    if gender_preferences is None:
        gender_preferences = ["female", "male"]

    u = User(
        id=uuid.uuid4(),
        telegram_id=telegram_id,
        username=None,
        registration_completed=registration_completed,
    )
    session.add(u)
    await session.flush()
    p = Profile(
        user_id=u.id,
        display_name=display_name,
        bio=None,
        birth_date=birth_date,
        gender=gender,
        city=city,
        district=None,
        latitude=latitude,
        longitude=longitude,
        interests=None,
        completeness_score=50,
        updated_at=datetime.now(timezone.utc),
    )
    session.add(p)
    pref = UserPreferences(
        user_id=u.id,
        age_min=age_min,
        age_max=age_max,
        gender_preferences=gender_preferences,
        max_distance_km=max_distance_km,
        updated_at=datetime.now(timezone.utc),
    )
    session.add(pref)
    if combined_rating is not None:
        session.add(
            UserRating(
                user_id=u.id,
                primary_score=0.5,
                behavioral_score=0.5,
                referral_bonus=0.0,
                combined_score=combined_rating,
                breakdown=None,
                algorithm_version="test",
            )
        )
    await session.commit()
    await session.refresh(u)
    return u


async def insert_user_ready_for_registration_complete(
    session: AsyncSession,
    *,
    telegram_id: int,
    photo_count: int | None = None,
) -> User:
    """User at ``optional_profile`` with search prefs + enough photos to call ``POST /registration/complete``."""
    n_photos = photo_count if photo_count is not None else settings.registration_min_photos
    if n_photos < settings.registration_min_photos:
        n_photos = settings.registration_min_photos

    u = await insert_user_with_profile(
        session,
        telegram_id=telegram_id,
        display_name="Ready User",
        birth_date=date(1998, 4, 12),
        gender="female",
        city="Berlin",
        latitude=52.52,
        longitude=13.405,
        registration_completed=False,
        age_min=20,
        age_max=40,
        gender_preferences=["male"],
        max_distance_km=50,
    )
    for i in range(n_photos):
        session.add(
            ProfilePhoto(
                id=uuid.uuid4(),
                profile_id=u.id,
                s3_key=f"profiles/{u.id}/p{i}.jpg",
                telegram_file_id=f"file-{i}",
                sort_order=i + 1,
            )
        )
    await session.commit()
    await session.refresh(u)
    return u
