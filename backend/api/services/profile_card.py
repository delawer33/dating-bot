"""Shared profile card serialization (discovery + /profile/me)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date

from botocore.client import BaseClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from shared.db.models import Profile, ProfilePhoto
from shared.storage.s3 import presigned_get_url

logger = logging.getLogger(__name__)


def age_on_date(birth: date, on: date) -> int:
    return (
        on.year
        - birth.year
        - ((on.month, on.day) < (birth.month, birth.day))
    )


async def build_profile_card(
    session: AsyncSession,
    profile_user_id: uuid.UUID,
    s3_client: BaseClient | None,
) -> dict:
    """Discovery-style card dict: text fields + `photos` ordered by sort_order (all photos)."""
    profile = await session.get(Profile, profile_user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    age = None
    if profile.birth_date:
        age = age_on_date(profile.birth_date, date.today())

    photos_result = await session.execute(
        select(ProfilePhoto)
        .where(ProfilePhoto.profile_id == profile_user_id)
        .order_by(ProfilePhoto.sort_order.asc())
    )
    rows = list(photos_result.scalars().all())
    photos_out: list[dict] = []
    for row in rows:
        url = None
        if s3_client and row.s3_key:
            try:
                url = await asyncio.to_thread(
                    presigned_get_url,
                    s3_client,
                    settings.s3_bucket,
                    row.s3_key,
                    3600,
                )
            except Exception:
                logger.exception("Presign failed for %s", row.s3_key)
        photos_out.append(
            {
                "id": row.id,
                "telegram_file_id": row.telegram_file_id,
                "presigned_url": url,
                "sort_order": row.sort_order,
            }
        )
    interests_out: list[str] | None = None
    raw_in = profile.interests
    if isinstance(raw_in, list):
        interests_out = [str(x) for x in raw_in]

    return {
        "target_user_id": profile_user_id,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "interests": interests_out,
        "age": age,
        "city": profile.city,
        "gender": profile.gender,
        "photos": photos_out,
    }
