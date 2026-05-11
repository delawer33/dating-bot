"""SQL candidate ranking and optional distance filter."""

from __future__ import annotations

import uuid
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import desc, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Profile, ProfileInteraction, User, UserPreferences, UserRating
from shared.geo.distance import haversine_km

from .constants import PREFETCH_BATCH, RANK_FETCH_CAP


async def rank_candidate_ids(
    session: AsyncSession,
    viewer_id: uuid.UUID,
    viewer_prefs: UserPreferences,
    viewer_profile: Profile | None,
) -> list[uuid.UUID]:
    today = date.today()
    interacted = select(ProfileInteraction.target_user_id).where(
        ProfileInteraction.actor_user_id == viewer_id
    )

    stmt = (
        select(User.id)
        .join(UserPreferences, UserPreferences.user_id == User.id)
        .join(Profile, Profile.user_id == User.id)
        .outerjoin(UserRating, UserRating.user_id == User.id)
        .where(User.id != viewer_id)
        .where(User.is_active.is_(True))
        .where(User.id.not_in(interacted))
        .where(Profile.birth_date.isnot(None))
        .where(Profile.gender.isnot(None))
    )

    if viewer_prefs.age_min is not None and viewer_prefs.age_max is not None:
        lo_bd = today - relativedelta(years=viewer_prefs.age_max)
        hi_bd = today - relativedelta(years=viewer_prefs.age_min)
        stmt = stmt.where(Profile.birth_date >= lo_bd, Profile.birth_date <= hi_bd)

    if viewer_prefs.gender_preferences:
        stmt = stmt.where(Profile.gender.in_(viewer_prefs.gender_preferences))

    stmt = stmt.order_by(
        nulls_last(desc(UserRating.combined_score)),
        User.created_at.asc(),
    ).limit(RANK_FETCH_CAP)

    result = await session.execute(stmt)
    raw_ids = list(result.scalars().all())

    if (
        viewer_prefs.max_distance_km is not None
        and viewer_profile
        and viewer_profile.latitude is not None
        and viewer_profile.longitude is not None
        and raw_ids
    ):
        max_km = float(viewer_prefs.max_distance_km)
        loc_result = await session.execute(
            select(Profile.user_id, Profile.latitude, Profile.longitude).where(
                Profile.user_id.in_(raw_ids)
            )
        )
        loc_by_user: dict[uuid.UUID, tuple[float, float]] = {}
        for uid, lat, lon in loc_result.all():
            if lat is not None and lon is not None:
                loc_by_user[uid] = (float(lat), float(lon))
        filtered: list[uuid.UUID] = []
        vlat, vlon = viewer_profile.latitude, viewer_profile.longitude
        for cand_id in raw_ids:
            loc = loc_by_user.get(cand_id)
            if loc is None:
                continue
            plat, plon = loc
            if haversine_km(vlat, vlon, plat, plon) <= max_km:
                filtered.append(cand_id)
        raw_ids = filtered

    return raw_ids[:PREFETCH_BATCH]
