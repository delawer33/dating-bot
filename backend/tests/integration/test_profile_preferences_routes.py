"""Profile and preferences HTTP routes with mocked service layer."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tests.conftest import BOT_AUTH_HEADERS


def _me_payload() -> dict:
    uid = uuid.uuid4()
    return {
        "user_id": str(uid),
        "is_complete": True,
        "registration_step": "complete",
        "profile": {
            "target_user_id": str(uid),
            "completeness_score": 70,
            "display_name": "Self",
            "bio": "Hi",
            "interests": ["music"],
            "age": 25,
            "city": "Paris",
            "gender": "other",
            "photos": [],
        },
        "preferences": {
            "age_min": 18,
            "age_max": 40,
            "gender_preferences": ["female"],
            "max_distance_km": 30,
        },
    }


def test_profile_me_ok(api_client_overridden_session: tuple[TestClient, object, object]) -> None:
    tc, _, _ = api_client_overridden_session
    with patch(
        "api.routers.profile.profile_svc.get_profile_me",
        new_callable=AsyncMock,
        return_value=_me_payload(),
    ):
        resp = tc.post("/profile/me", json={"telegram_id": 555111}, headers=BOT_AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_complete"] is True
    assert data["registration_step"] == "complete"
    assert data["profile"]["display_name"] == "Self"


def test_profile_display_name_ok(
    api_client_overridden_session: tuple[TestClient, object, object],
) -> None:
    tc, _, _ = api_client_overridden_session
    with patch("api.routers.profile.pe.edit_display_name", new_callable=AsyncMock) as m:
        resp = tc.post(
            "/profile/display-name",
            json={"telegram_id": 555111, "display_name": "NewName"},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    m.assert_awaited_once()


def test_profile_location_ok(api_client_overridden_session: tuple[TestClient, object, object]) -> None:
    tc, _, _ = api_client_overridden_session
    with patch("api.routers.profile.pe.edit_location", new_callable=AsyncMock) as m:
        resp = tc.post(
            "/profile/location",
            json={"telegram_id": 555111, "latitude": 52.5, "longitude": 13.4},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    m.assert_awaited_once()


def test_profile_photo_delete_ok(
    api_client_overridden_session: tuple[TestClient, object, object],
) -> None:
    tc, _, _ = api_client_overridden_session
    pid = str(uuid.uuid4())
    with patch("api.routers.profile.pe.delete_profile_photo", new_callable=AsyncMock) as m:
        resp = tc.post(
            "/profile/photo/delete",
            json={"telegram_id": 555111, "photo_id": pid},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    m.assert_awaited_once()


def test_preferences_age_range_ok(
    api_client_overridden_session: tuple[TestClient, object, object],
) -> None:
    tc, _, _ = api_client_overridden_session
    with patch("api.routers.preferences.pref_edit.edit_age_range", new_callable=AsyncMock) as m:
        resp = tc.post(
            "/preferences/age-range",
            json={"telegram_id": 555111, "age_min": 21, "age_max": 45},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    m.assert_awaited_once()


def test_preferences_gender_ok(api_client_overridden_session: tuple[TestClient, object, object]) -> None:
    tc, _, _ = api_client_overridden_session
    with patch(
        "api.routers.preferences.pref_edit.edit_gender_preferences",
        new_callable=AsyncMock,
    ) as m:
        resp = tc.post(
            "/preferences/gender",
            json={"telegram_id": 555111, "gender_preferences": ["male", "female"]},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    m.assert_awaited_once()


def test_preferences_max_distance_ok(
    api_client_overridden_session: tuple[TestClient, object, object],
) -> None:
    tc, _, _ = api_client_overridden_session
    with patch(
        "api.routers.preferences.pref_edit.edit_max_distance",
        new_callable=AsyncMock,
    ) as m:
        resp = tc.post(
            "/preferences/max-distance",
            json={"telegram_id": 555111, "max_distance_km": 75},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    m.assert_awaited_once()
