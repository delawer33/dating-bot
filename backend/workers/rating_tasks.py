"""Celery tasks — sync wrappers around async rating persistence."""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import rating_service
from shared.db.models import User, UserPreferences
from workers.celery_app import celery_app
from workers.db import create_async_engine_and_sessionmaker

logger = logging.getLogger(__name__)


async def _recompute_one(session: AsyncSession, user_id: uuid.UUID) -> None:
    await rating_service.recompute_user_rating(session, user_id)


async def _async_recompute_user(user_id: str) -> None:
    engine, factory = create_async_engine_and_sessionmaker()
    try:
        async with factory() as session:
            async with session.begin():
                await _recompute_one(session, uuid.UUID(user_id))
    finally:
        await engine.dispose()


async def _async_recompute_all() -> None:
    engine, factory = create_async_engine_and_sessionmaker()
    try:
        async with factory() as session:
            result = await session.execute(select(User.id).join(UserPreferences))
            ids = list(result.scalars().all())
        for uid in ids:
            async with factory() as s2:
                async with s2.begin():
                    await _recompute_one(s2, uid)
            logger.debug("Recomputed rating for %s", uid)
        logger.info("Recomputed ratings for %d users", len(ids))
    finally:
        await engine.dispose()


@celery_app.task(name="rating.recompute_user")
def recompute_user_ratings_task(user_id: str) -> None:
    asyncio.run(_async_recompute_user(user_id))


@celery_app.task(name="rating.recompute_all")
def recompute_all_ratings_task() -> None:
    asyncio.run(_async_recompute_all())
