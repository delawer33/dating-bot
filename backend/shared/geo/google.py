import httpx
from shared.geo.provider import GeoLocation, GeocodingError

_BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_TIMEOUT = 5.0


class GoogleMapsProvider:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def reverse_geocode(self, lat: float, lon: float) -> GeoLocation:
        params = {"latlng": f"{lat},{lon}", "key": self._api_key}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(_BASE_URL, params=params)

        if response.status_code != 200:
            raise GeocodingError(f"Google Maps HTTP {response.status_code}")

        data = response.json()
        if data.get("status") != "OK" or not data.get("results"):
            raise GeocodingError(f"Google Maps status: {data.get('status')}")

        components = data["results"][0].get("address_components", [])
        city = _extract_component(components, "locality") or _extract_component(
            components, "administrative_area_level_2"
        )
        if not city:
            raise GeocodingError("Google Maps: city not found in response")

        district = _extract_component(components, "sublocality_level_1") or _extract_component(
            components, "sublocality"
        )
        return GeoLocation(city=city, district=district)


def _extract_component(components: list[dict], type_name: str) -> str | None:
    for comp in components:
        if type_name in comp.get("types", []):
            return comp.get("long_name")
    return None
