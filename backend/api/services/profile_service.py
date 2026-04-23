"""Current user profile read API."""

from __future__ import annotations

from botocore.client import BaseClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.services import registration_service as reg_svc
from api.services.profile_card import build_profile_card
from api.services.profile_photo_service import count_profile_photos
from shared.db.models import Profile, User


async def get_profile_me(
    session: AsyncSession,
    telegram_id: int,
    s3_client: BaseClient | None,
) -> dict:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    profile = await session.get(Profile, user.id)
    prefs = await reg_svc.get_preferences_if_exists(session, user.id)
    n_photos = await count_profile_photos(session, user.id) if profile is not None else 0
    step = reg_svc.registration_step_from_data(
        profile,
        registration_completed=user.registration_completed,
        photo_count=n_photos,
        prefs=prefs,
        min_photos=settings.registration_min_photos,
    )

    profile_payload = None
    if profile is not None:
        card = await build_profile_card(session, user.id, s3_client)
        profile_payload = {**card, "completeness_score": int(profile.completeness_score)}

    prefs_payload = None
    if prefs is not None:
        prefs_payload = {
            "age_min": prefs.age_min,
            "age_max": prefs.age_max,
            "gender_preferences": list(prefs.gender_preferences)
            if prefs.gender_preferences
            else None,
            "max_distance_km": prefs.max_distance_km,
        }

    return {
        "user_id": user.id,
        "is_complete": user.registration_completed,
        "registration_step": step,
        "profile": profile_payload,
        "preferences": prefs_payload,
    }
