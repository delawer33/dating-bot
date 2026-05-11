"""Celery rating task async helpers (no broker, no DB)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workers import rating_tasks as rt


@pytest.fixture(autouse=True)
def reset_worker_db_pool() -> None:
    rt._worker_engine = None
    rt._worker_session_factory = None
    yield
    rt._worker_engine = None
    rt._worker_session_factory = None


@pytest.mark.asyncio
async def test_async_recompute_user_calls_rating_service() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()

    @asynccontextmanager
    async def begin() -> object:
        yield None

    session.begin = MagicMock(side_effect=begin)

    @asynccontextmanager
    async def open_session() -> object:
        yield session

    factory = MagicMock(return_value=open_session())
    engine = AsyncMock()

    with patch(
        "workers.rating_tasks.create_async_engine_and_sessionmaker",
        return_value=(engine, factory),
    ):
        with patch.object(rt.rating_service, "recompute_user_rating", new_callable=AsyncMock) as rec:
            await rt._async_recompute_user(str(uid))

    rec.assert_awaited_once_with(session, uid)


@pytest.mark.asyncio
async def test_async_recompute_all_calls_recompute_per_user() -> None:
    uid_a, uid_b = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock()

    @asynccontextmanager
    async def begin() -> object:
        yield None

    session.begin = MagicMock(side_effect=begin)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [uid_a, uid_b]
    session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def open_session() -> object:
        yield session

    factory = MagicMock(return_value=open_session())
    engine = AsyncMock()

    with patch(
        "workers.rating_tasks.create_async_engine_and_sessionmaker",
        return_value=(engine, factory),
    ):
        with patch.object(rt, "_recompute_one", new_callable=AsyncMock) as rec:
            await rt._async_recompute_all()

    assert rec.await_count == 2
    assert rec.await_args_list[0].args[1] == uid_a
    assert rec.await_args_list[1].args[1] == uid_b
