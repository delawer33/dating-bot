import logging
from collections.abc import Callable

from shared.geo.provider import GeoLocation, GeocodingError, GeocodingProvider

logger = logging.getLogger(__name__)

_geocode_metrics_hook: Callable[[str, str], None] | None = None


def set_geocode_metrics_hook(hook: Callable[[str, str], None] | None) -> None:
    """Optional callback ``(provider_class_name, outcome)`` with outcome ``success`` or ``failure``."""
    global _geocode_metrics_hook
    _geocode_metrics_hook = hook


class CascadeGeocodingProvider:
    def __init__(self, providers: list[GeocodingProvider]) -> None:
        if not providers:
            raise ValueError("At least one geocoding provider is required")
        self._providers = providers

    async def reverse_geocode(self, lat: float, lon: float) -> GeoLocation:
        last_error: Exception | None = None
        for provider in self._providers:
            pname = type(provider).__name__
            try:
                loc = await provider.reverse_geocode(lat, lon)
                if _geocode_metrics_hook is not None:
                    _geocode_metrics_hook(pname, "success")
                return loc
            except Exception as exc:
                if _geocode_metrics_hook is not None:
                    _geocode_metrics_hook(pname, "failure")
                logger.warning("Geocoding provider %s failed: %s", pname, exc)
                last_error = exc

        raise GeocodingError(f"All geocoding providers failed: {last_error}") from last_error
