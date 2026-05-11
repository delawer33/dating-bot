"""Full ASGI stack over real Postgres + Redis (dependency overrides only skip lifespan / broker)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from api.dependencies import get_event_publisher, get_redis
from api.main import create_app
from shared.db.models import ProfileInteraction, User
from shared.db.session import get_session
from tests.conftest import BOT_AUTH_HEADERS
from tests.factories.users import insert_user_ready_for_registration_complete, insert_user_with_profile

pytestmark = pytest.mark.integration_db


@pytest.fixture
def http_app(
    db_session: AsyncSession,
    redis_client: Any,
    noop_publisher: Any,
) -> AsyncIterator[Any]:
    app = create_app(use_lifespan=False)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _redis_override() -> Any:
        return redis_client

    def _publisher_override(request: Request) -> Any:
        return noop_publisher

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_redis] = _redis_override
    app.dependency_overrides[get_event_publisher] = _publisher_override
    yield app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_registration_complete_via_http_persists(
    http_app: Any,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.services.task_helpers.schedule_rating_recompute",
        lambda *_a, **_k: None,
    )
    u = await insert_user_ready_for_registration_complete(db_session, telegram_id=880_001)

    transport = ASGITransport(app=http_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/registration/complete",
            json={"telegram_id": u.telegram_id},
            headers=BOT_AUTH_HEADERS,
        )
    assert r.status_code == 200
    data = r.json()
    assert data["is_complete"] is True

    row = await db_session.get(User, u.id)
    assert row is not None
    assert row.registration_completed is True


@pytest.mark.asyncio
async def test_discovery_like_via_http(
    http_app: Any,
    db_session: AsyncSession,
) -> None:
    from datetime import date

    a = await insert_user_with_profile(
        db_session,
        telegram_id=880_010,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["male"],
    )
    b = await insert_user_with_profile(
        db_session,
        telegram_id=880_011,
        gender="male",
        birth_date=date(1994, 1, 1),
        gender_preferences=["female"],
    )

    transport = ASGITransport(app=http_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/discovery/like",
            json={"telegram_id": a.telegram_id, "target_user_id": str(b.id)},
            headers=BOT_AUTH_HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is False

    row = await db_session.scalar(
        select(ProfileInteraction.id).where(
            ProfileInteraction.actor_user_id == a.id,
            ProfileInteraction.target_user_id == b.id,
            ProfileInteraction.action == "like",
        )
    )
    assert row is not None


@pytest.mark.asyncio
async def test_discovery_skip_via_http(
    http_app: Any,
    db_session: AsyncSession,
) -> None:
    from datetime import date

    a = await insert_user_with_profile(
        db_session,
        telegram_id=880_020,
        gender="female",
        birth_date=date(1996, 1, 1),
        gender_preferences=["male"],
    )
    b = await insert_user_with_profile(
        db_session,
        telegram_id=880_021,
        gender="male",
        birth_date=date(1994, 1, 1),
        gender_preferences=["female"],
    )

    transport = ASGITransport(app=http_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/discovery/skip",
            json={"telegram_id": a.telegram_id, "target_user_id": str(b.id)},
            headers=BOT_AUTH_HEADERS,
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    row = await db_session.scalar(
        select(ProfileInteraction.id).where(
            ProfileInteraction.actor_user_id == a.id,
            ProfileInteraction.target_user_id == b.id,
            ProfileInteraction.action == "skip",
        )
    )
    assert row is not None


@pytest.mark.asyncio
async def test_missing_bot_secret_returns_401_before_db(
    http_app: Any,
) -> None:
    """Router-level auth must reject requests without touching dependency overrides for DB."""
    transport = ASGITransport(app=http_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/registration/complete",
            json={"telegram_id": 1},
            headers={k: v for k, v in BOT_AUTH_HEADERS.items() if k.lower() != "x-bot-secret"},
        )
    assert r.status_code == 401
