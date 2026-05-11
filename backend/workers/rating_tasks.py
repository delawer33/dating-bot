"""Celery tasks — sync wrappers around async rating persistence."""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.services import rating_service
from shared.db.models import User, UserPreferences
from workers.celery_app import celery_app
from workers.db import create_async_engine_and_sessionmaker

logger = logging.getLogger(__name__)

_worker_engine: AsyncEngine | None = None
_worker_session_factory: async_sessionmaker[AsyncSession] | None = None


def _worker_session_factory_get() -> async_sessionmaker[AsyncSession]:
    global _worker_engine, _worker_session_factory
    if _worker_session_factory is None:
        _worker_engine, _worker_session_factory = create_async_engine_and_sessionmaker()
    return _worker_session_factory


async def _recompute_one(session: AsyncSession, user_id: uuid.UUID) -> None:
    await rating_service.recompute_user_rating(session, user_id)


async def _async_recompute_user(user_id: str) -> None:
    factory = _worker_session_factory_get()
    async with factory() as session:
        async with session.begin():
            await _recompute_one(session, uuid.UUID(user_id))


async def _async_recompute_all() -> None:
    factory = _worker_session_factory_get()
    async with factory() as session:
        async with session.begin():
            result = await session.execute(select(User.id).join(UserPreferences))
            ids = list(result.scalars().all())
        for uid in ids:
            async with session.begin():
                await _recompute_one(session, uid)
            logger.debug("Recomputed rating for %s", uid)
    logger.info("Recomputed ratings for %d users", len(ids))


@celery_app.task(name="rating.recompute_user")
def recompute_user_ratings_task(user_id: str) -> None:
    asyncio.run(_async_recompute_user(user_id))


@celery_app.task(name="rating.recompute_all")
def recompute_all_ratings_task() -> None:
    asyncio.run(_async_recompute_all())
