"""Unit tests for bot.utils.api_errors.format_http_error."""

from __future__ import annotations

import httpx

from bot.utils.api_errors import format_http_error


def _http_error(status_code: int, json: dict | None = None, content: bytes | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/v1/test")
    if json is not None:
        response = httpx.Response(status_code=status_code, json=json, request=request)
    else:
        response = httpx.Response(status_code=status_code, content=content or b"", request=request)
    return httpx.HTTPStatusError("HTTP error", request=request, response=response)


def test_format_http_error_string_detail() -> None:
    exc = _http_error(400, {"detail": "  Неверный токен  "})
    assert format_http_error(exc) == "Неверный токен"


def test_format_http_error_string_detail_truncated() -> None:
    long_msg = "x" * 1200
    exc = _http_error(400, {"detail": long_msg})
    out = format_http_error(exc, max_len=100)
    assert len(out) == 100
    assert out.endswith("…")


def test_format_http_error_list_detail_pydantic() -> None:
    exc = _http_error(
        422,
        {
            "detail": [
                {
                    "loc": ["body", "age_max"],
                    "msg": "Input should be less than or equal to 120",
                    "type": "less_than_equal",
                    "ctx": {"le": 120},
                }
            ]
        },
    )
    text = format_http_error(exc)
    assert "Максимальный возраст в поиске" in text
    assert "120" in text


def test_format_http_error_list_multiple_items() -> None:
    exc = _http_error(
        422,
        {
            "detail": [
                {"loc": ["body", "age_min"], "msg": "x", "type": "greater_than_equal", "ctx": {"ge": 18}},
                {"loc": ["body", "max_distance_km"], "msg": "y", "type": "less_than_equal", "ctx": {"le": 500}},
            ]
        },
    )
    text = format_http_error(exc)
    assert "Минимальный возраст" in text or "возраст" in text.lower()
    assert "расстояние" in text.lower() or "500" in text


def test_format_http_error_empty_detail_list() -> None:
    exc = _http_error(422, {"detail": []})
    assert "422" in format_http_error(exc)


def test_format_http_error_invalid_json_body() -> None:
    exc = _http_error(500, content=b"not json")
    out = format_http_error(exc)
    assert "500" in out
    assert "Позже" in out or "сервер" in out.lower()
