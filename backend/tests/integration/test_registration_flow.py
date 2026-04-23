"""Integration tests for the full registration flow via the FastAPI test client.

These tests require no real DB; they stub the DB session and geocoder via
FastAPI's dependency override mechanism.
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import get_geocoding_provider, get_redis, get_session
from shared.geo.provider import GeoLocation


# ── DB and Redis stubs ─────────────────────────────────────────────────────────

def _stub_session():
    """Minimal async DB session that records calls without touching a real DB."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def _stub_redis():
    return AsyncMock()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    """TestClient with DB, Redis, and geocoder overridden."""
    from unittest.mock import patch

    session_stub = _stub_session()
    redis_stub = _stub_redis()

    async def _session_override():
        yield session_stub

    async def _redis_override():
        return redis_stub

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_redis] = _redis_override
    yield TestClient(app), session_stub
    app.dependency_overrides.clear()


_BOT_SECRET = "test-secret"
_HEADERS = {"X-Bot-Secret": _BOT_SECRET}
_TG_ID = 111222333


# ── Auth guard ────────────────────────────────────────────────────────────────

def test_registration_requires_bot_secret(client) -> None:
    tc, _ = client
    resp = tc.post("/registration/start", json={"telegram_id": _TG_ID})
    assert resp.status_code == 401


# ── /start – new user ─────────────────────────────────────────────────────────

def test_start_new_user(client) -> None:
    tc, session = client

    user_id = uuid.uuid4()
    new_user = MagicMock()
    new_user.id = user_id
    new_user.telegram_id = _TG_ID
    new_user.username = "testuser"
    new_user.registration_completed = False

    # First execute returns no existing user (None), second returns the new user.
    from sqlalchemy.engine import Result
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None

    with_user = MagicMock()
    with_user.scalar_one_or_none.return_value = new_user

    # referral_code is absent → no referrer query. get_registration_state loads user,
    # profile, then prefs inside _get_registration_step.
    session.execute.side_effect = [
        no_result,   # registration_start: user by telegram_id → not found
        with_user,  # get_registration_state: user by telegram_id
        no_result,   # profile by user_id → none
        no_result,   # preferences by user_id → none
    ]
    session.refresh.side_effect = lambda obj: setattr(obj, "id", user_id)

    resp = tc.post(
        "/registration/start",
        json={"telegram_id": _TG_ID, "username": "testuser"},
        headers=_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["telegram_id"] == _TG_ID
    assert data["registration_step"] == "display_name"
    assert data["is_new_user"] is True
    assert data["is_complete"] is False


# ── /health – no auth needed ──────────────────────────────────────────────────

def test_health_returns_ok() -> None:
    with TestClient(app) as tc:
        resp = tc.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
