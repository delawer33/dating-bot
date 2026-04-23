"""Post-registration search preferences (per-block)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.registration import GenderValue
from api.services import registration_service as reg_svc
from shared.db.models import User


async def _user_by_telegram(session: AsyncSession, telegram_id: int) -> User:
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    u = r.scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return u


def _require_done(user: User) -> None:
    if not user.registration_completed:
        raise HTTPException(
            status_code=403,
            detail="Finish registration before changing search preferences.",
        )


async def edit_age_range(
    session: AsyncSession, telegram_id: int, age_min: int, age_max: int
):
    user = await _user_by_telegram(session, telegram_id)
    _require_done(user)
    reg_svc._validate_search_age_range(age_min, age_max)
    prefs = await reg_svc.get_or_create_user_preferences(session, user.id)
    prefs.age_min = age_min
    prefs.age_max = age_max
    prefs.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(prefs)
    return prefs


async def edit_gender_preferences(
    session: AsyncSession, telegram_id: int, gender_preferences: list[GenderValue]
):
    user = await _user_by_telegram(session, telegram_id)
    _require_done(user)
    prefs = await reg_svc.get_or_create_user_preferences(session, user.id)
    prefs.gender_preferences = list(gender_preferences)
    prefs.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(prefs)
    return prefs


async def edit_max_distance(session: AsyncSession, telegram_id: int, max_distance_km: int):
    user = await _user_by_telegram(session, telegram_id)
    _require_done(user)
    reg_svc._validate_max_distance_km(max_distance_km)
    prefs = await reg_svc.get_or_create_user_preferences(session, user.id)
    prefs.max_distance_km = max_distance_km
    prefs.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(prefs)
    return prefs
