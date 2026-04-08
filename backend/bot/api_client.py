from datetime import date
from typing import Any

import httpx

from bot.config import settings
from bot.resilience import ApiUnavailableError, CircuitBreaker, retry_with_backoff

_HEADERS = {"X-Bot-Secret": settings.api_secret}
_TIMEOUT = 1.0

_circuit_breaker = CircuitBreaker(failure_threshold=5, open_timeout=30.0)


async def _post(path: str, body: dict) -> dict[str, Any]:
    url = f"{settings.api_base_url}{path}"

    async def _call() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(url, json=body, headers=_HEADERS)
        response.raise_for_status()
        return response.json()

    return await _circuit_breaker.execute(lambda: retry_with_backoff(_call))


async def registration_start(
    telegram_id: int,
    username: str | None,
    referral_code: str | None,
) -> dict[str, Any]:
    return await _post(
        "/registration/start",
        {
            "telegram_id": telegram_id,
            "username": username,
            "referral_code": referral_code,
        },
    )


async def set_display_name(telegram_id: int, display_name: str) -> dict[str, Any]:
    return await _post(
        "/registration/display-name",
        {"telegram_id": telegram_id, "display_name": display_name},
    )


async def set_birth_date(telegram_id: int, birth_date: date) -> dict[str, Any]:
    return await _post(
        "/registration/birth-date",
        {"telegram_id": telegram_id, "birth_date": birth_date.isoformat()},
    )


async def set_gender(telegram_id: int, gender: str) -> dict[str, Any]:
    return await _post(
        "/registration/gender",
        {"telegram_id": telegram_id, "gender": gender},
    )


async def set_location(
    telegram_id: int, latitude: float, longitude: float
) -> dict[str, Any]:
    return await _post(
        "/registration/location",
        {"telegram_id": telegram_id, "latitude": latitude, "longitude": longitude},
    )


async def complete_registration(telegram_id: int) -> dict[str, Any]:
    return await _post(
        "/registration/complete",
        {"telegram_id": telegram_id},
    )
