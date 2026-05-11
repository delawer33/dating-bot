"""Redis-backed discovery prefetch queue."""

from __future__ import annotations

import uuid

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Profile, User, UserPreferences

from .constants import DISCOVERY_QUEUE_KEY, DISCOVERY_TTL_SEC, PREFETCH_BATCH
from .ranking import rank_candidate_ids


def queue_key(viewer_id: uuid.UUID) -> str:
    return DISCOVERY_QUEUE_KEY.format(viewer_id=str(viewer_id))


async def top_up_redis_queue(
    redis: aioredis.Redis,
    session: AsyncSession,
    viewer: User,
    viewer_prefs: UserPreferences,
) -> None:
    key = queue_key(viewer.id)
    viewer_profile = await session.get(Profile, viewer.id)
    ranked = await rank_candidate_ids(session, viewer.id, viewer_prefs, viewer_profile)
    if not ranked:
        return
    batch = [str(x) for x in ranked[:PREFETCH_BATCH]]
    pipe = redis.pipeline(transaction=False)
    pipe.delete(key)
    pipe.rpush(key, *batch)
    pipe.expire(key, DISCOVERY_TTL_SEC)
    await pipe.execute()


async def pop_next_target_id(
    redis: aioredis.Redis,
    session: AsyncSession,
    viewer: User,
    viewer_prefs: UserPreferences,
) -> uuid.UUID | None:
    key = queue_key(viewer.id)
    target_raw = await redis.lpop(key)
    if target_raw is None:
        await top_up_redis_queue(redis, session, viewer, viewer_prefs)
        target_raw = await redis.lpop(key)
    if target_raw is None:
        return None
    remaining = await redis.llen(key)
    if remaining <= 2:
        await top_up_redis_queue(redis, session, viewer, viewer_prefs)
    return uuid.UUID(str(target_raw))


async def invalidate_discovery_queue(redis: aioredis.Redis, viewer_id: uuid.UUID) -> None:
    await redis.delete(queue_key(viewer_id))
