"""Bot HTTP client — mocked transport, no real API."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import httpx
import pytest

import bot.api_client as ac
from bot.resilience import CircuitBreaker


@pytest.mark.asyncio
async def test_registration_start_posts_expected_path(monkeypatch: pytest.MonkeyPatch) -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"ok": True, "telegram_id": 1})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://api.test")
    prev = ac._http_client
    monkeypatch.setattr(ac, "_http_client", client)
    monkeypatch.setattr(ac, "_circuit_breaker", CircuitBreaker(failure_threshold=99, open_timeout=30.0))
    monkeypatch.setattr(ac.settings, "api_base_url", "http://api.test")
    try:
        out = await ac.registration_start(telegram_id=1, username="u", referral_code=None)
    finally:
        await client.aclose()
        monkeypatch.setattr(ac, "_http_client", prev)

    assert out["ok"] is True
    assert paths == ["/registration/start"]


@pytest.mark.asyncio
async def test_discovery_like_posts_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies: list[dict] = []
    tid = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "matched": False,
                "match_id": None,
                "peer_display_name": None,
                "peer_telegram_id": None,
                "peer_username": None,
                "target_user_id": str(tid),
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://api.test")
    prev = ac._http_client
    monkeypatch.setattr(ac, "_http_client", client)
    monkeypatch.setattr(ac, "_circuit_breaker", CircuitBreaker(failure_threshold=99, open_timeout=30.0))
    monkeypatch.setattr(ac.settings, "api_base_url", "http://api.test")
    try:
        await ac.discovery_like(telegram_id=42, target_user_id=str(tid))
    finally:
        await client.aclose()
        monkeypatch.setattr(ac, "_http_client", prev)

    assert bodies == [{"telegram_id": 42, "target_user_id": str(tid)}]
