"""Nominatim requires a non-empty User-Agent per the OSM usage policy."""
import httpx
from shared.geo.provider import GeoLocation, GeocodingError

_BASE_URL = "https://nominatim.openstreetmap.org/reverse"
_TIMEOUT = 5.0


class NominatimProvider:
    def __init__(self, user_agent: str = "DatingBot/1.0") -> None:
        self._user_agent = user_agent

    async def reverse_geocode(self, lat: float, lon: float) -> GeoLocation:
        params = {"lat": lat, "lon": lon, "format": "json", "zoom": 14}
        headers = {"User-Agent": self._user_agent}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(_BASE_URL, params=params, headers=headers)

        if response.status_code != 200:
            raise GeocodingError(f"Nominatim HTTP {response.status_code}")

        address = response.json().get("address", {})
        city = _extract_city(address)
        if not city:
            raise GeocodingError("Nominatim: city not found in response")

        return GeoLocation(city=city, district=_extract_district(address))


def _extract_city(address: dict) -> str | None:
    # OSM hierarchy: city > town > village > municipality > county
    for key in ("city", "town", "village", "municipality", "county"):
        if value := address.get(key):
            return value
    return None


def _extract_district(address: dict) -> str | None:
    for key in ("suburb", "neighbourhood", "district", "city_district", "quarter"):
        if value := address.get(key):
            return value
    return None
