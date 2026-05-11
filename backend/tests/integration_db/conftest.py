"""Postgres + Redis via testcontainers for integration_db tests."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration_db.migrations import alembic_upgrade_head

try:
    from testcontainers.core.docker_client import DockerClient
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer
except ImportError:  # pragma: no cover
    DockerClient = None  # type: ignore[misc, assignment]
    PostgresContainer = None  # type: ignore[misc, assignment]
    RedisContainer = None  # type: ignore[misc, assignment]


def _docker_available() -> bool:
    if os.environ.get("INTEGRATION_DB") == "0":
        return False
    if DockerClient is None:
        return False
    try:
        DockerClient().client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_url() -> str:
    if not _docker_available():
        pytest.skip("Docker unavailable or INTEGRATION_DB=0; skipping integration_db tests")
    assert PostgresContainer is not None
    with PostgresContainer("postgres:15-alpine") as pg:
        url = pg.get_connection_url(driver="asyncpg")
        alembic_upgrade_head(url)
        yield url


@pytest.fixture(scope="session")
def redis_url() -> str:
    if not _docker_available():
        pytest.skip("Docker unavailable or INTEGRATION_DB=0; skipping integration_db tests")
    assert RedisContainer is not None
    with RedisContainer("redis:7-alpine") as rc:
        host = rc.get_container_host_ip()
        port = rc.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
async def db_session(postgres_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(postgres_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def noop_publisher() -> Any:
    """Minimal stand-in for EventPublisher (like/skip only need awaitable no-ops)."""

    class _Pub:
        async def publish_profile_liked(self, **_: object) -> None:
            return None

        async def publish_profile_skipped(self, **_: object) -> None:
            return None

        async def publish_match_created(self, **_: object) -> None:
            return None

    return _Pub()
