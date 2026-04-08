from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeoLocation:
    city: str
    district: str | None


class GeocodingProvider(Protocol):
    async def reverse_geocode(self, lat: float, lon: float) -> GeoLocation: ...


class GeocodingError(Exception):
    """Raised when all providers fail to resolve coordinates."""
