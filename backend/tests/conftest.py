"""Shared pytest fixtures."""
import os

import pytest

# Point all config classes to a test .env so they don't read backend/.env
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("BOT_SECRET", "test-secret")
os.environ.setdefault("BOT_TOKEN", "0:test-token")
os.environ.setdefault("API_BASE_URL", "http://api:8000")
os.environ.setdefault("API_SECRET", "test-secret")
