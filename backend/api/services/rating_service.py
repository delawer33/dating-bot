"""Persist computed ratings for a user."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import rating_algorithms as ra
from shared.db.models import Profile, ReferralEvent, User, UserBehaviorStats, UserPreferences, UserRating


async def count_successful_referrals(session: AsyncSession, referrer_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(ReferralEvent).where(ReferralEvent.referrer_id == referrer_id)
    )
    return int(result.scalar_one() or 0)


async def recompute_user_rating(session: AsyncSession, user_id: uuid.UUID) -> UserRating:
    user = await session.get(User, user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")

    profile = await session.get(Profile, user_id)
    prefs = await session.get(UserPreferences, user_id)
    stats_row = await session.get(UserBehaviorStats, user_id)

    completeness = int(profile.completeness_score) if profile else 0
    has_distance_pref = bool(prefs and prefs.max_distance_km is not None)
    primary = ra.compute_primary_score(completeness, has_distance_pref)

    stats_input = None
    if stats_row:
        stats_input = ra.BehaviorInputs(
            likes_received=stats_row.likes_received,
            skips_received=stats_row.skips_received,
            matches_count=stats_row.matches_count,
        )
    behavioral, behavioral_detail = ra.compute_behavioral_score(stats_input)

    ref_count = await count_successful_referrals(session, user_id)
    referral_bonus, referral_detail = ra.compute_referral_bonus(ref_count)

    combined = ra.compute_combined(primary, behavioral, referral_bonus)
    breakdown = ra.build_breakdown(
        primary=primary,
        behavioral=behavioral,
        referral_bonus=referral_bonus,
        combined=combined,
        behavioral_detail=behavioral_detail,
        referral_detail=referral_detail,
        has_distance_pref=has_distance_pref,
    )

    now = datetime.now(timezone.utc)
    stmt = (
        insert(UserRating)
        .values(
            user_id=user_id,
            primary_score=primary,
            behavioral_score=behavioral,
            referral_bonus=referral_bonus,
            combined_score=combined,
            breakdown=breakdown,
            algorithm_version=ra.ALGORITHM_VERSION,
            computed_at=now,
        )
        .on_conflict_do_update(
            index_elements=[UserRating.user_id],
            set_={
                "primary_score": primary,
                "behavioral_score": behavioral,
                "referral_bonus": referral_bonus,
                "combined_score": combined,
                "breakdown": breakdown,
                "algorithm_version": ra.ALGORITHM_VERSION,
                "computed_at": now,
            },
        )
    )
    await session.execute(stmt)
    await session.flush()
    row = await session.get(UserRating, user_id)
    assert row is not None
    return row
