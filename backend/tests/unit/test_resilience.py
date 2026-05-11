"""Circuit breaker and retry helpers used by the bot API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from bot.resilience import ApiUnavailableError, CircuitBreaker, retry_with_backoff


@pytest.mark.asyncio
async def test_retry_with_backoff_non_retryable_4xx() -> None:
    async def boom() -> None:
        req = httpx.Request("GET", "http://example.test/x")
        resp = httpx.Response(404, request=req)
        raise httpx.HTTPStatusError("not found", request=req, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        await retry_with_backoff(boom)


@pytest.mark.asyncio
async def test_retry_with_backoff_succeeds_after_5xx() -> None:
    n = {"c": 0}

    async def flaky() -> str:
        n["c"] += 1
        if n["c"] < 2:
            req = httpx.Request("GET", "http://example.test/x")
            resp = httpx.Response(503, request=req)
            raise httpx.HTTPStatusError("svc", request=req, response=resp)
        return "ok"

    with patch("bot.resilience.asyncio.sleep", new_callable=AsyncMock):
        out = await retry_with_backoff(flaky)
    assert out == "ok"
    assert n["c"] == 2


@pytest.mark.asyncio
async def test_retry_with_backoff_exhausted() -> None:
    async def always_5xx() -> None:
        req = httpx.Request("GET", "http://example.test/x")
        resp = httpx.Response(500, request=req)
        raise httpx.HTTPStatusError("err", request=req, response=resp)

    with patch("bot.resilience.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ApiUnavailableError):
            await retry_with_backoff(always_5xx)


@pytest.mark.asyncio
async def test_circuit_breaker_open_rejects() -> None:
    cb = CircuitBreaker(failure_threshold=1, open_timeout=3600.0)

    async def boom() -> None:
        req = httpx.Request("GET", "http://example.test/x")
        resp = httpx.Response(500, request=req)
        raise httpx.HTTPStatusError("err", request=req, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        await cb.execute(boom)
    with pytest.raises(ApiUnavailableError, match="OPEN"):
        await cb.execute(boom)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_to_closed() -> None:
    cb = CircuitBreaker(failure_threshold=1, open_timeout=0.0)

    async def boom() -> None:
        req = httpx.Request("GET", "http://example.test/x")
        resp = httpx.Response(500, request=req)
        raise httpx.HTTPStatusError("err", request=req, response=resp)

    async def ok() -> str:
        return "fine"

    with pytest.raises(httpx.HTTPStatusError):
        await cb.execute(boom)
    with patch("bot.resilience.time.monotonic", return_value=1_000_000.0):
        out = await cb.execute(ok)
    assert out == "fine"
