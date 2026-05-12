"""HTTP smoke for registration router (create_app without lifespan, stub session)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_geocoding_provider
from api.main import create_app
from shared.db.session import get_session
from shared.geo.provider import GeoLocation
from tests.conftest import BOT_AUTH_HEADERS


@pytest.fixture
async def reg_client():
    app = create_app(use_lifespan=False)
    app.state.s3_client = MagicMock()
    geo = MagicMock()
    geo.reverse_geocode = AsyncMock(return_value=GeoLocation(city="X", district=None))
    app.dependency_overrides[get_geocoding_provider] = lambda: geo

    session_stub = AsyncMock()
    session_stub.execute = AsyncMock()
    session_stub.commit = AsyncMock()
    session_stub.refresh = AsyncMock()
    session_stub.flush = AsyncMock()
    session_stub.add = MagicMock()

    async def _sess():
        yield session_stub

    app.dependency_overrides[get_session] = _sess
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac, session_stub
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_registration_routes_smoke(reg_client) -> None:
    ac, _ = reg_client
    uid = uuid.uuid4()
    state = {
        "user_id": str(uid),
        "telegram_id": 800001,
        "registration_step": "display_name",
        "is_complete": False,
        "photo_count": 0,
    }

    with patch("api.routers.registration.svc.registration_start", new_callable=AsyncMock, return_value=(MagicMock(), True)):
        with patch("api.routers.registration.svc.get_registration_state", new_callable=AsyncMock, return_value=state):
            r = await ac.post(
                "/registration/start",
                json={"telegram_id": 800001},
                headers=BOT_AUTH_HEADERS,
            )
            assert r.status_code == 200

    with patch("api.routers.registration.svc.get_referral_info", new_callable=AsyncMock, return_value={"referral_code": "ABC", "invite_link": None}):
        r = await ac.post("/registration/referral", json={"telegram_id": 800001}, headers=BOT_AUTH_HEADERS)
        assert r.status_code == 200

    for path, body, patch_target, _ in [
        ("/registration/display-name", {"telegram_id": 800001, "display_name": "N"}, "set_display_name", AsyncMock()),
        ("/registration/birth-date", {"telegram_id": 800001, "birth_date": "1999-01-01"}, "set_birth_date", AsyncMock()),
        ("/registration/gender", {"telegram_id": 800001, "gender": "female"}, "set_gender", AsyncMock()),
        (
            "/registration/location",
            {"telegram_id": 800001, "latitude": 1.0, "longitude": 2.0},
            "set_location",
            AsyncMock(),
        ),
        ("/registration/photo", {"telegram_id": 800001, "file_id": "f"}, "add_registration_photo", AsyncMock()),
        (
            "/registration/search-preferences/age-range",
            {"telegram_id": 800001, "age_min": 18, "age_max": 40},
            "set_registration_search_age",
            AsyncMock(),
        ),
        (
            "/registration/search-preferences/gender",
            {"telegram_id": 800001, "gender_preferences": ["male"]},
            "set_registration_search_gender",
            AsyncMock(),
        ),
        (
            "/registration/search-preferences/distance",
            {"telegram_id": 800001, "max_distance_km": 30},
            "set_registration_search_distance",
            AsyncMock(),
        ),
        ("/registration/bio", {"telegram_id": 800001, "bio": "Hi"}, "set_registration_bio", AsyncMock()),
        (
            "/registration/interests",
            {"telegram_id": 800001, "interest_ids": ["music"]},
            "set_registration_interests",
            AsyncMock(),
        ),
        ("/registration/complete", {"telegram_id": 800001}, "complete_registration", AsyncMock()),
    ]:
        with patch(f"api.routers.registration.svc.{patch_target}", new_callable=AsyncMock):
            with patch("api.routers.registration.svc.get_registration_state", new_callable=AsyncMock, return_value=state):
                r = await ac.post(path, json=body, headers=BOT_AUTH_HEADERS)
                assert r.status_code == 200, (path, r.text)
