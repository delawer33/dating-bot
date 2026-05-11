"""Discovery HTTP routes — service layer mocked; DB/Redis overridden via conftest."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tests.conftest import BOT_AUTH_HEADERS


def test_discovery_next_unauthorized() -> None:
    from api.main import app

    with TestClient(app) as tc:
        resp = tc.post("/discovery/next", json={"telegram_id": 1})
    assert resp.status_code == 401


def test_discovery_next_ok(api_client_overridden_session: tuple[TestClient, object, object]) -> None:
    tc, _, _ = api_client_overridden_session
    tid = uuid.uuid4()
    body = {
        "profile": {
            "target_user_id": str(tid),
            "display_name": "Ann",
            "bio": None,
            "interests": [],
            "age": 28,
            "city": "Berlin",
            "gender": "female",
            "photos": [],
        },
        "exhausted": False,
    }
    with patch("api.routers.discovery.disc.get_next_profile", new_callable=AsyncMock, return_value=body):
        resp = tc.post("/discovery/next", json={"telegram_id": 424242}, headers=BOT_AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["exhausted"] is False
    assert data["profile"]["display_name"] == "Ann"


def test_discovery_like_ok(api_client_overridden_session: tuple[TestClient, object, object]) -> None:
    tc, _, _ = api_client_overridden_session
    target = uuid.uuid4()
    out = {
        "matched": True,
        "match_id": str(uuid.uuid4()),
        "peer_display_name": "Bob",
        "peer_telegram_id": 999,
        "peer_username": "bob",
        "target_user_id": target,
    }
    with patch("api.routers.discovery.disc.record_like", new_callable=AsyncMock, return_value=out):
        resp = tc.post(
            "/discovery/like",
            json={"telegram_id": 424242, "target_user_id": str(target)},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched"] is True
    assert data["peer_telegram_id"] == 999


def test_discovery_skip_ok(api_client_overridden_session: tuple[TestClient, object, object]) -> None:
    tc, _, _ = api_client_overridden_session
    target = uuid.uuid4()
    with patch(
        "api.routers.discovery.disc.record_skip",
        new_callable=AsyncMock,
        return_value={"ok": True, "target_user_id": target},
    ):
        resp = tc.post(
            "/discovery/skip",
            json={"telegram_id": 424242, "target_user_id": str(target)},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_discovery_incoming_likes_inbox(
    api_client_overridden_session: tuple[TestClient, object, object],
) -> None:
    tc, _, _ = api_client_overridden_session
    iid = uuid.uuid4()
    aid = uuid.uuid4()
    rows = [
        {
            "interaction_id": iid,
            "actor_user_id": aid,
            "created_at": "2026-01-01T12:00:00",
            "actor_display_name": "X",
            "is_matched": False,
            "actor_telegram_id": None,
            "actor_username": None,
            "profile": None,
        }
    ]
    with patch(
        "api.routers.discovery.disc.list_incoming_likes_inbox",
        new_callable=AsyncMock,
        return_value=rows,
    ):
        resp = tc.post(
            "/discovery/incoming-likes",
            json={"telegram_id": 424242, "mode": "inbox", "limit": 10},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    likes = resp.json()["likes"]
    assert len(likes) == 1
    assert likes[0]["actor_display_name"] == "X"


def test_discovery_incoming_likes_history(
    api_client_overridden_session: tuple[TestClient, object, object],
) -> None:
    tc, _, _ = api_client_overridden_session
    with patch(
        "api.routers.discovery.disc.list_incoming_likes",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = tc.post(
            "/discovery/incoming-likes",
            json={"telegram_id": 424242, "mode": "history", "limit": 5},
            headers=BOT_AUTH_HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["likes"] == []
