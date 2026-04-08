import logging

from shared.geo.provider import GeoLocation, GeocodingError, GeocodingProvider

logger = logging.getLogger(__name__)


class CascadeGeocodingProvider:
    def __init__(self, providers: list[GeocodingProvider]) -> None:
        if not providers:
            raise ValueError("At least one geocoding provider is required")
        self._providers = providers

    async def reverse_geocode(self, lat: float, lon: float) -> GeoLocation:
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                return await provider.reverse_geocode(lat, lon)
            except Exception as exc:
                logger.warning("Geocoding provider %s failed: %s", type(provider).__name__, exc)
                last_error = exc

        raise GeocodingError(f"All geocoding providers failed: {last_error}") from last_error
