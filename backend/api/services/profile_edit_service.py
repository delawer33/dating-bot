"""Post-registration profile edits (per-block)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone

import redis.asyncio as aioredis
from botocore.client import BaseClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.schemas.registration import GenderValue
from api.services import registration_service as reg_svc
from api.services.discovery_service import invalidate_discovery_queue
from api.services.profile_photo_service import add_photo_from_telegram, count_profile_photos
from api.services.registration_service import _validate_age, compute_profile_completeness
from shared.db.models import Profile, ProfilePhoto, User
from shared.geo.cascade import CascadeGeocodingProvider
from shared.geo.provider import GeocodingError
from shared.interests_taxonomy import VALID_INTEREST_IDS
from shared.storage.s3 import delete_object


async def _user_by_telegram(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _require_registration_done(user: User) -> None:
    if not user.registration_completed:
        raise HTTPException(
            status_code=403,
            detail="Finish registration before changing profile settings.",
        )


async def edit_display_name(session: AsyncSession, telegram_id: int, display_name: str) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    profile = await reg_svc.get_or_create_profile(session, user.id)
    n_photos = await count_profile_photos(session, user.id)
    profile.display_name = display_name
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = compute_profile_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def edit_birth_date(session: AsyncSession, telegram_id: int, birth_date: date) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    _validate_age(birth_date)
    profile = await reg_svc.get_or_create_profile(session, user.id)
    n_photos = await count_profile_photos(session, user.id)
    profile.birth_date = birth_date
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = compute_profile_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def edit_gender(session: AsyncSession, telegram_id: int, gender: GenderValue) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    profile = await reg_svc.get_or_create_profile(session, user.id)
    n_photos = await count_profile_photos(session, user.id)
    profile.gender = gender
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = compute_profile_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def edit_location(
    session: AsyncSession,
    redis: aioredis.Redis,
    telegram_id: int,
    lat: float,
    lon: float,
    geocoder: CascadeGeocodingProvider,
) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    profile = await reg_svc.get_or_create_profile(session, user.id)
    n_photos = await count_profile_photos(session, user.id)
    try:
        geo = await geocoder.reverse_geocode(lat, lon)
    except GeocodingError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not determine city from coordinates: {exc}",
        ) from exc
    profile.city = geo.city
    profile.district = geo.district
    profile.latitude = lat
    profile.longitude = lon
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = compute_profile_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    await invalidate_discovery_queue(redis, user.id)
    return profile


async def edit_bio(session: AsyncSession, telegram_id: int, bio: str) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    if len(bio) > settings.profile_bio_max_length:
        raise HTTPException(
            status_code=422,
            detail=f"Bio cannot exceed {settings.profile_bio_max_length} characters.",
        )
    profile = await reg_svc.get_or_create_profile(session, user.id)
    n_photos = await count_profile_photos(session, user.id)
    profile.bio = bio or None
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = compute_profile_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def edit_interests(session: AsyncSession, telegram_id: int, interest_ids: list[str]) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    if len(interest_ids) > settings.profile_max_interests:
        raise HTTPException(
            status_code=422,
            detail=f"At most {settings.profile_max_interests} interests.",
        )
    unknown = [x for x in interest_ids if x not in VALID_INTEREST_IDS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown interest ids: {unknown}")
    profile = await reg_svc.get_or_create_profile(session, user.id)
    n_photos = await count_profile_photos(session, user.id)
    profile.interests = list(interest_ids) if interest_ids else None
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = compute_profile_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def add_profile_photo(
    session: AsyncSession,
    telegram_id: int,
    file_id: str,
    s3_client: BaseClient,
) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    profile = await reg_svc.get_or_create_profile(session, user.id)
    return await add_photo_from_telegram(
        session,
        user.id,
        profile,
        file_id,
        s3_client,
        max_photos=settings.registration_max_photos,
        recalc_completeness=compute_profile_completeness,
    )


async def delete_profile_photo(
    session: AsyncSession,
    s3_client: BaseClient,
    telegram_id: int,
    photo_id: uuid.UUID,
) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    profile = await reg_svc.get_or_create_profile(session, user.id)
    row = await session.get(ProfilePhoto, photo_id)
    if row is None or row.profile_id != user.id:
        raise HTTPException(status_code=404, detail="Photo not found.")
    n_before = await count_profile_photos(session, user.id)
    if n_before <= settings.registration_min_photos:
        raise HTTPException(
            status_code=422,
            detail=f"At least {settings.registration_min_photos} photo(s) must remain.",
        )
    await asyncio.to_thread(delete_object, s3_client, settings.s3_bucket, row.s3_key)
    await session.delete(row)
    await session.flush()
    remaining = (
        await session.execute(
            select(ProfilePhoto)
            .where(ProfilePhoto.profile_id == user.id)
            .order_by(ProfilePhoto.sort_order.asc())
        )
    ).scalars().all()
    for i, ph in enumerate(remaining, start=1):
        ph.sort_order = i
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = compute_profile_completeness(profile, len(remaining))
    await session.commit()
    await session.refresh(profile)
    return profile


async def reorder_profile_photos(
    session: AsyncSession,
    telegram_id: int,
    photo_ids: list[uuid.UUID],
) -> Profile:
    user = await _user_by_telegram(session, telegram_id)
    _require_registration_done(user)
    profile = await reg_svc.get_or_create_profile(session, user.id)
    existing = (
        await session.execute(
            select(ProfilePhoto).where(ProfilePhoto.profile_id == user.id)
        )
    ).scalars().all()
    by_id = {p.id: p for p in existing}
    if len(photo_ids) != len(by_id):
        raise HTTPException(status_code=422, detail="photo_ids must list every profile photo once.")
    for pid in photo_ids:
        if pid not in by_id:
            raise HTTPException(status_code=422, detail="Unknown photo id in list.")
    for order, pid in enumerate(photo_ids, start=1):
        by_id[pid].sort_order = order
    profile.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(profile)
    return profile
