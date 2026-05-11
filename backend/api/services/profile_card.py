"""Shared profile card serialization (discovery + /profile/me)."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.photo_presign import PhotoPresigner
from shared.db.models import Profile, ProfilePhoto


def age_on_date(birth: date, on: date) -> int:
    return (
        on.year
        - birth.year
        - ((on.month, on.day) < (birth.month, birth.day))
    )


def _card_payload_from_profile(profile: Profile, profile_user_id: uuid.UUID) -> dict:
    age = None
    if profile.birth_date:
        age = age_on_date(profile.birth_date, date.today())
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
        "photos": [],  # filled by callers
    }


async def build_profile_cards_for_users(
    session: AsyncSession,
    user_ids: list[uuid.UUID],
    presigner: PhotoPresigner | None,
) -> dict[uuid.UUID, dict]:
    """Batch-load profiles + photos; presign in parallel. Skips ids with no profile row."""
    if not user_ids:
        return {}
    prof_result = await session.execute(
        select(Profile).where(Profile.user_id.in_(user_ids))
    )
    profiles: dict[uuid.UUID, Profile] = {
        p.user_id: p for p in prof_result.scalars().all()
    }
    photo_result = await session.execute(
        select(ProfilePhoto)
        .where(ProfilePhoto.profile_id.in_(user_ids))
        .order_by(ProfilePhoto.profile_id.asc(), ProfilePhoto.sort_order.asc())
    )
    photos_by_user: dict[uuid.UUID, list[ProfilePhoto]] = defaultdict(list)
    for ph in photo_result.scalars().all():
        photos_by_user[ph.profile_id].append(ph)

    presign_coros: list = []
    presign_index: list[tuple[uuid.UUID, int]] = []
    out: dict[uuid.UUID, dict] = {}

    for uid in user_ids:
        profile = profiles.get(uid)
        if not profile:
            continue
        card = _card_payload_from_profile(profile, uid)
        rows = photos_by_user.get(uid, [])
        photo_dicts: list[dict] = []
        for i, row in enumerate(rows):
            photo_dicts.append(
                {
                    "id": row.id,
                    "telegram_file_id": row.telegram_file_id,
                    "presigned_url": None,
                    "sort_order": row.sort_order,
                }
            )
            if presigner and row.s3_key:
                presign_index.append((uid, i))
                presign_coros.append(presigner.presign(row.s3_key))
        card["photos"] = photo_dicts
        out[uid] = card

    if presign_coros:
        signed = await asyncio.gather(*presign_coros)
        for (uid, idx), url in zip(presign_index, signed, strict=True):
            out[uid]["photos"][idx]["presigned_url"] = url

    return out


async def build_profile_card(
    session: AsyncSession,
    profile_user_id: uuid.UUID,
    presigner: PhotoPresigner | None,
) -> dict:
    """Discovery-style card dict: text fields + `photos` ordered by sort_order (all photos)."""
    profile = await session.get(Profile, profile_user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    photos_result = await session.execute(
        select(ProfilePhoto)
        .where(ProfilePhoto.profile_id == profile_user_id)
        .order_by(ProfilePhoto.sort_order.asc())
    )
    rows = list(photos_result.scalars().all())
    photos_out: list[dict] = []
    presign_coros: list = []
    presign_slots: list[int] = []
    for i, row in enumerate(rows):
        photos_out.append(
            {
                "id": row.id,
                "telegram_file_id": row.telegram_file_id,
                "presigned_url": None,
                "sort_order": row.sort_order,
            }
        )
        if presigner and row.s3_key:
            presign_slots.append(i)
            presign_coros.append(presigner.presign(row.s3_key))
    if presign_coros:
        urls = await asyncio.gather(*presign_coros)
        for slot, url in zip(presign_slots, urls, strict=True):
            photos_out[slot]["presigned_url"] = url

    card = _card_payload_from_profile(profile, profile_user_id)
    card["photos"] = photos_out
    return card
