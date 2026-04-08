"""Unit tests for geocoding providers and the cascade chain."""
import pytest
import httpx
from pytest_httpx import HTTPXMock

from shared.geo.nominatim import NominatimProvider
from shared.geo.google import GoogleMapsProvider
from shared.geo.cascade import CascadeGeocodingProvider
from shared.geo.provider import GeocodingError


# ── Nominatim ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nominatim_returns_city_and_district(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url__contains="nominatim.openstreetmap.org",
        json={
            "address": {
                "city": "Moscow",
                "suburb": "Arbat",
            }
        },
    )
    provider = NominatimProvider()
    result = await provider.reverse_geocode(55.75, 37.62)
    assert result.city == "Moscow"
    assert result.district == "Arbat"


@pytest.mark.asyncio
async def test_nominatim_falls_back_to_town(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url__contains="nominatim.openstreetmap.org",
        json={"address": {"town": "Mytishchi"}},
    )
    provider = NominatimProvider()
    result = await provider.reverse_geocode(55.91, 37.73)
    assert result.city == "Mytishchi"
    assert result.district is None


@pytest.mark.asyncio
async def test_nominatim_raises_on_empty_city(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url__contains="nominatim.openstreetmap.org",
        json={"address": {}},
    )
    provider = NominatimProvider()
    with pytest.raises(GeocodingError):
        await provider.reverse_geocode(0.0, 0.0)


@pytest.mark.asyncio
async def test_nominatim_raises_on_http_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url__contains="nominatim.openstreetmap.org",
        status_code=503,
    )
    provider = NominatimProvider()
    with pytest.raises(GeocodingError):
        await provider.reverse_geocode(55.75, 37.62)


# ── Google Maps ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_returns_city_and_district(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url__contains="maps.googleapis.com",
        json={
            "status": "OK",
            "results": [
                {
                    "address_components": [
                        {"long_name": "Moscow", "types": ["locality"]},
                        {"long_name": "Arbat District", "types": ["sublocality_level_1"]},
                    ]
                }
            ],
        },
    )
    provider = GoogleMapsProvider(api_key="test-key")
    result = await provider.reverse_geocode(55.75, 37.62)
    assert result.city == "Moscow"
    assert result.district == "Arbat District"


@pytest.mark.asyncio
async def test_google_raises_on_zero_results(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url__contains="maps.googleapis.com",
        json={"status": "ZERO_RESULTS", "results": []},
    )
    provider = GoogleMapsProvider(api_key="test-key")
    with pytest.raises(GeocodingError):
        await provider.reverse_geocode(0.0, 0.0)


# ── Cascade ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cascade_uses_primary(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url__contains="nominatim.openstreetmap.org",
        json={"address": {"city": "Moscow"}},
    )
    cascade = CascadeGeocodingProvider([NominatimProvider()])
    result = await cascade.reverse_geocode(55.75, 37.62)
    assert result.city == "Moscow"


@pytest.mark.asyncio
async def test_cascade_falls_back_to_google(httpx_mock: HTTPXMock) -> None:
    # Nominatim fails with 500.
    httpx_mock.add_response(
        url__contains="nominatim.openstreetmap.org",
        status_code=500,
    )
    # Google succeeds.
    httpx_mock.add_response(
        url__contains="maps.googleapis.com",
        json={
            "status": "OK",
            "results": [
                {
                    "address_components": [
                        {"long_name": "Saint Petersburg", "types": ["locality"]}
                    ]
                }
            ],
        },
    )
    cascade = CascadeGeocodingProvider(
        [NominatimProvider(), GoogleMapsProvider(api_key="k")]
    )
    result = await cascade.reverse_geocode(59.95, 30.32)
    assert result.city == "Saint Petersburg"


@pytest.mark.asyncio
async def test_cascade_raises_when_all_fail(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url__contains="nominatim.openstreetmap.org", status_code=500)
    httpx_mock.add_response(url__contains="maps.googleapis.com", status_code=500)
    cascade = CascadeGeocodingProvider(
        [NominatimProvider(), GoogleMapsProvider(api_key="k")]
    )
    with pytest.raises(GeocodingError):
        await cascade.reverse_geocode(0.0, 0.0)


def test_cascade_requires_at_least_one_provider() -> None:
    with pytest.raises(ValueError):
        CascadeGeocodingProvider([])
