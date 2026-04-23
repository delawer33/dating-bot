"""Format FastAPI / httpx API errors for Telegram users (Russian)."""

from __future__ import annotations

from typing import Any

import httpx


def _field_hint(loc: list[str | int]) -> str:
    str_parts = [str(x) for x in loc if isinstance(x, str)]
    skip = frozenset({"body", "query", "path", "header", "cookie"})
    last_field = next((p for p in reversed(str_parts) if p not in skip), "")
    hints: dict[str, str] = {
        "age_min": "Минимальный возраст в поиске",
        "age_max": "Максимальный возраст в поиске",
        "max_distance_km": "Макс. расстояние (км)",
        "display_name": "Имя",
        "birth_date": "Дата рождения",
        "gender": "Пол",
        "latitude": "Широта",
        "longitude": "Долгота",
        "interest_ids": "Интересы",
        "photo_ids": "Порядок фото",
        "photo_id": "Фото",
    }
    if last_field in hints:
        return hints[last_field]
    return last_field or "Поле"


def _one_error_line(err: dict[str, Any]) -> str:
    msg = str(err.get("msg", "ошибка"))
    loc = err.get("loc") or []
    if not isinstance(loc, list):
        loc = []
    field = _field_hint(loc)
    if "less_than_equal" in msg or err.get("type") == "less_than_equal":
        ctx = err.get("ctx") or {}
        le = ctx.get("le")
        if le is not None:
            return f"{field}: значение не больше {le}."
        return f"{field}: слишком большое значение."
    if "greater_than_equal" in msg or err.get("type") == "greater_than_equal":
        ctx = err.get("ctx") or {}
        ge = ctx.get("ge")
        if ge is not None:
            return f"{field}: значение не меньше {ge}."
        return f"{field}: слишком маленькое значение."
    if "int_parsing" in str(err.get("type", "")):
        return f"{field}: нужно целое число."
    if "missing" in str(err.get("type", "")):
        return f"{field}: обязательное поле."
    return f"{field}: {msg}"


def format_http_error(exc: httpx.HTTPStatusError, *, max_len: int = 900) -> str:
    """User-visible single message from httpx error (handles FastAPI 422 list detail)."""
    resp = exc.response
    try:
        payload = resp.json()
    except Exception:
        return f"Ошибка сервера (код {resp.status_code}). Попробуйте позже."

    detail = payload.get("detail")
    if isinstance(detail, str):
        text = detail.strip() or f"Ошибка (код {resp.status_code})."
        return text if len(text) <= max_len else text[: max_len - 1] + "…"

    if isinstance(detail, list) and detail:
        lines: list[str] = []
        for item in detail[:5]:
            if isinstance(item, dict):
                lines.append(_one_error_line(item))
            else:
                lines.append(str(item))
        text = " ".join(x for x in lines if x).strip()
        if not text:
            text = f"Ошибка проверки данных (код {resp.status_code})."
        return text if len(text) <= max_len else text[: max_len - 1] + "…"

    return f"Ошибка (код {resp.status_code}). Попробуйте позже."
