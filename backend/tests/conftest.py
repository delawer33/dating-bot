"""Shared pytest fixtures."""
import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

# Point all config classes to a test .env so they don't read backend/.env
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
os.environ.setdefault("BOT_SECRET", "test-secret")
os.environ.setdefault("BOT_TOKEN", "0:test-token")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minio")
os.environ.setdefault("S3_SECRET_KEY", "minio")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("API_BASE_URL", "http://api:8000")
os.environ.setdefault("API_SECRET", "test-secret")


@pytest.fixture(autouse=True)
def _noop_s3_ensure_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lifespan calls ensure_bucket against S3/MinIO; tests must not require a real bucket."""
    from api import main as api_main

    monkeypatch.setattr(api_main, "ensure_bucket", lambda _client, _bucket: None)


def stub_session() -> AsyncMock:
    """Minimal async DB session for API tests (no real DB)."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def stub_redis() -> AsyncMock:
    return AsyncMock()


@pytest.fixture()
def api_client_overridden_session() -> AsyncIterator[tuple[object, AsyncMock, AsyncMock]]:
    """FastAPI TestClient with DB + Redis dependencies overridden (lifespan still runs)."""
    from fastapi.testclient import TestClient

    from api.dependencies import get_redis, get_session
    from api.main import app

    session_stub = stub_session()
    redis_stub = stub_redis()

    async def _session_override() -> AsyncIterator[AsyncMock]:
        yield session_stub

    async def _redis_override() -> AsyncMock:
        return redis_stub

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_redis] = _redis_override
    with TestClient(app) as tc:
        yield tc, session_stub, redis_stub
    app.dependency_overrides.clear()


BOT_AUTH_HEADERS = {"X-Bot-Secret": os.environ["BOT_SECRET"]}
