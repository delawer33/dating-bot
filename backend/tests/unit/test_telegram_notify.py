"""Tests for workers.telegram_notify.send_telegram_text."""

from __future__ import annotations

import pytest

from workers.telegram_notify import send_telegram_text


@pytest.mark.asyncio
async def test_send_telegram_text_success(httpx_mock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:TEST_TOKEN")
    httpx_mock.add_response(
        method="POST",
        url="https://api.telegram.org/bot123:TEST_TOKEN/sendMessage",
        json={"ok": True, "result": {"message_id": 1}},
    )
    ok = await send_telegram_text(999001, "hello")
    assert ok is True
    req = httpx_mock.get_request()
    assert req is not None
    body = req.content.decode()
    assert "999001" in body
    assert "hello" in body


@pytest.mark.asyncio
async def test_send_telegram_text_no_token_skips(
    httpx_mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    ok = await send_telegram_text(1, "x")
    assert ok is False
    assert len(httpx_mock.get_requests()) == 0


@pytest.mark.asyncio
async def test_send_telegram_text_api_error(httpx_mock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:TEST_TOKEN")
    httpx_mock.add_response(
        method="POST",
        url="https://api.telegram.org/bot123:TEST_TOKEN/sendMessage",
        status_code=400,
        text="Bad Request",
    )
    ok = await send_telegram_text(1, "x")
    assert ok is False
