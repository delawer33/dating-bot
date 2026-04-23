from datetime import date
from typing import Any

import httpx

from bot.config import settings
from bot.resilience import ApiUnavailableError, CircuitBreaker, retry_with_backoff

_HEADERS = {"X-Bot-Secret": settings.api_secret}
_DEFAULT_TIMEOUT = 1.0
_DISCOVERY_TIMEOUT = 12.0

_circuit_breaker = CircuitBreaker(failure_threshold=5, open_timeout=30.0)
_http_client: httpx.AsyncClient | None = None


async def init_api_http() -> None:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(headers=_HEADERS)


async def close_api_http() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def _post(path: str, body: dict, *, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    if _http_client is None:
        raise RuntimeError("API HTTP client not initialized; call init_api_http() from bot startup.")
    url = f"{settings.api_base_url}{path}"

    async def _call() -> dict[str, Any]:
        response = await _http_client.post(url, json=body, timeout=timeout)
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


async def registration_referral(telegram_id: int) -> dict[str, Any]:
    return await _post("/registration/referral", {"telegram_id": telegram_id})


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


async def add_registration_photo(telegram_id: int, file_id: str) -> dict[str, Any]:
    return await _post(
        "/registration/photo",
        {"telegram_id": telegram_id, "file_id": file_id},
    )


async def complete_registration(telegram_id: int) -> dict[str, Any]:
    return await _post(
        "/registration/complete",
        {"telegram_id": telegram_id},
    )


async def discovery_next(telegram_id: int) -> dict[str, Any]:
    return await _post(
        "/discovery/next",
        {"telegram_id": telegram_id},
        timeout=_DISCOVERY_TIMEOUT,
    )


async def discovery_like(telegram_id: int, target_user_id: str) -> dict[str, Any]:
    return await _post(
        "/discovery/like",
        {"telegram_id": telegram_id, "target_user_id": target_user_id},
        timeout=_DISCOVERY_TIMEOUT,
    )


async def discovery_skip(telegram_id: int, target_user_id: str) -> dict[str, Any]:
    return await _post(
        "/discovery/skip",
        {"telegram_id": telegram_id, "target_user_id": target_user_id},
        timeout=_DISCOVERY_TIMEOUT,
    )


async def discovery_incoming_likes(
    telegram_id: int,
    *,
    mode: str = "inbox",
    limit: int = 10,
) -> dict[str, Any]:
    return await _post(
        "/discovery/incoming-likes",
        {"telegram_id": telegram_id, "mode": mode, "limit": limit},
        timeout=_DISCOVERY_TIMEOUT,
    )


async def profile_me(telegram_id: int) -> dict[str, Any]:
    return await _post(
        "/profile/me",
        {"telegram_id": telegram_id},
        timeout=_DISCOVERY_TIMEOUT,
    )


async def registration_search_age(
    telegram_id: int, age_min: int, age_max: int
) -> dict[str, Any]:
    return await _post(
        "/registration/search-preferences/age-range",
        {"telegram_id": telegram_id, "age_min": age_min, "age_max": age_max},
    )


async def registration_search_gender(
    telegram_id: int, gender_preferences: list[str]
) -> dict[str, Any]:
    return await _post(
        "/registration/search-preferences/gender",
        {"telegram_id": telegram_id, "gender_preferences": gender_preferences},
    )


async def registration_search_distance(telegram_id: int, max_distance_km: int) -> dict[str, Any]:
    return await _post(
        "/registration/search-preferences/distance",
        {"telegram_id": telegram_id, "max_distance_km": max_distance_km},
    )


async def registration_bio(telegram_id: int, bio: str) -> dict[str, Any]:
    return await _post(
        "/registration/bio",
        {"telegram_id": telegram_id, "bio": bio},
    )


async def registration_interests(telegram_id: int, interest_ids: list[str]) -> dict[str, Any]:
    return await _post(
        "/registration/interests",
        {"telegram_id": telegram_id, "interest_ids": interest_ids},
    )


async def profile_set_display_name(telegram_id: int, display_name: str) -> dict[str, Any]:
    return await _post(
        "/profile/display-name",
        {"telegram_id": telegram_id, "display_name": display_name},
    )


async def profile_set_birth_date(telegram_id: int, birth_date: date) -> dict[str, Any]:
    return await _post(
        "/profile/birth-date",
        {"telegram_id": telegram_id, "birth_date": birth_date.isoformat()},
    )


async def profile_set_gender(telegram_id: int, gender: str) -> dict[str, Any]:
    return await _post(
        "/profile/gender",
        {"telegram_id": telegram_id, "gender": gender},
    )


async def profile_set_location(
    telegram_id: int, latitude: float, longitude: float
) -> dict[str, Any]:
    return await _post(
        "/profile/location",
        {"telegram_id": telegram_id, "latitude": latitude, "longitude": longitude},
    )


async def profile_set_bio(telegram_id: int, bio: str) -> dict[str, Any]:
    return await _post(
        "/profile/bio",
        {"telegram_id": telegram_id, "bio": bio},
    )


async def profile_set_interests(telegram_id: int, interest_ids: list[str]) -> dict[str, Any]:
    return await _post(
        "/profile/interests",
        {"telegram_id": telegram_id, "interest_ids": interest_ids},
    )


async def profile_add_photo(telegram_id: int, file_id: str) -> dict[str, Any]:
    return await _post(
        "/profile/photo",
        {"telegram_id": telegram_id, "file_id": file_id},
    )


async def profile_delete_photo(telegram_id: int, photo_id: str) -> dict[str, Any]:
    return await _post(
        "/profile/photo/delete",
        {"telegram_id": telegram_id, "photo_id": photo_id},
    )


async def profile_reorder_photos(telegram_id: int, photo_ids: list[str]) -> dict[str, Any]:
    return await _post(
        "/profile/photo/reorder",
        {"telegram_id": telegram_id, "photo_ids": photo_ids},
    )


async def preferences_set_age(telegram_id: int, age_min: int, age_max: int) -> dict[str, Any]:
    return await _post(
        "/preferences/age-range",
        {"telegram_id": telegram_id, "age_min": age_min, "age_max": age_max},
    )


async def preferences_set_gender(telegram_id: int, gender_preferences: list[str]) -> dict[str, Any]:
    return await _post(
        "/preferences/gender",
        {"telegram_id": telegram_id, "gender_preferences": gender_preferences},
    )


async def preferences_set_distance(telegram_id: int, max_distance_km: int) -> dict[str, Any]:
    return await _post(
        "/preferences/max-distance",
        {"telegram_id": telegram_id, "max_distance_km": max_distance_km},
    )
