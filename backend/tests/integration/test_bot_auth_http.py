"""Bot secret is enforced on mutating routes before DB/session dependencies run."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,payload",
    [
        ("/registration/start", {"telegram_id": 1}),
        ("/registration/complete", {"telegram_id": 1}),
        ("/registration/referral", {"telegram_id": 1}),
        ("/registration/display-name", {"telegram_id": 1, "display_name": "A"}),
        ("/preferences/age-range", {"telegram_id": 1, "age_min": 18, "age_max": 30}),
        ("/preferences/gender", {"telegram_id": 1, "gender_preferences": ["male"]}),
        ("/preferences/max-distance", {"telegram_id": 1, "max_distance_km": 25}),
        ("/profile/me", {"telegram_id": 1}),
        ("/profile/display-name", {"telegram_id": 1, "display_name": "X"}),
        ("/discovery/next", {"telegram_id": 1}),
        (
            "/discovery/like",
            {"telegram_id": 1, "target_user_id": str(uuid.uuid4())},
        ),
        (
            "/discovery/skip",
            {"telegram_id": 1, "target_user_id": str(uuid.uuid4())},
        ),
        ("/discovery/incoming-likes", {"telegram_id": 1, "mode": "inbox"}),
    ],
)
async def test_post_without_bot_secret_returns_401(path: str, payload: dict) -> None:
    app = create_app(use_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(path, json=payload)
    assert r.status_code == 401, (path, r.text)
