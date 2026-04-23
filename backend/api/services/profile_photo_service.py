"""Upload profile photos from Telegram file_id → S3 (shared by registration and profile)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
from botocore.client import BaseClient
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from shared.db.models import Profile, ProfilePhoto
from shared.storage.s3 import delete_object, put_object


async def count_profile_photos(session: AsyncSession, profile_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(ProfilePhoto).where(ProfilePhoto.profile_id == profile_id)
    )
    return int(result.scalar_one() or 0)


async def add_photo_from_telegram(
    session: AsyncSession,
    user_id: uuid.UUID,
    profile: Profile,
    file_id: str,
    s3_client: BaseClient,
    *,
    max_photos: int,
    recalc_completeness: Callable[[Profile, int], int] | None = None,
) -> Profile:
    """Download from Telegram, store in S3, insert ProfilePhoto. Commits on success."""
    n_photos = await count_profile_photos(session, user_id)
    if n_photos >= max_photos:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {max_photos} photos.",
        )

    dup = (
        await session.execute(
            select(ProfilePhoto).where(
                ProfilePhoto.profile_id == user_id,
                ProfilePhoto.telegram_file_id == file_id,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        await session.refresh(profile)
        return profile

    from api.services import telegram_file_service as tg

    try:
        body, content_type = await tg.download_file_bytes(
            settings.bot_token, file_id, settings.telegram_file_max_size_bytes
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="Could not download file from Telegram."
        ) from exc

    ext = tg.extension_for_content_type(content_type)
    if ext not in ("jpg", "png", "webp"):
        raise HTTPException(status_code=422, detail="Invalid image type.")

    photo_id = uuid.uuid4()
    s3_key = f"profiles/{user_id}/{photo_id}.{ext}"
    await asyncio.to_thread(
        put_object, s3_client, settings.s3_bucket, s3_key, body, content_type, None
    )
    new_count = n_photos + 1
    session.add(
        ProfilePhoto(
            id=photo_id,
            profile_id=user_id,
            s3_key=s3_key,
            telegram_file_id=file_id,
            sort_order=new_count,
        )
    )
    profile.updated_at = datetime.now(timezone.utc)
    if recalc_completeness is not None:
        profile.completeness_score = recalc_completeness(profile, new_count)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        other = (
            await session.execute(
                select(ProfilePhoto).where(
                    ProfilePhoto.profile_id == user_id,
                    ProfilePhoto.telegram_file_id == file_id,
                )
            )
        ).scalar_one_or_none()
        if other is None:
            raise
        await asyncio.to_thread(delete_object, s3_client, settings.s3_bucket, s3_key)
        prof = (
            await session.execute(select(Profile).where(Profile.user_id == user_id))
        ).scalar_one_or_none()
        if prof is None:
            raise HTTPException(status_code=500, detail="Inconsistent profile state after duplicate save.")
        await session.refresh(prof)
        return prof

    await session.refresh(profile)
    return profile
