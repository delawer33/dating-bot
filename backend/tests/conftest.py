"""Shared pytest fixtures."""
import os

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
