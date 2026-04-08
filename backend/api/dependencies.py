import hmac
import logging
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from shared.db.session import get_session
from shared.geo.cascade import CascadeGeocodingProvider
from shared.geo.google import GoogleMapsProvider
from shared.geo.nominatim import NominatimProvider

logger = logging.getLogger(__name__)

_geocoding_provider: CascadeGeocodingProvider | None = None
_redis_client: aioredis.Redis | None = None


def build_geocoding_provider() -> CascadeGeocodingProvider:
    providers = [NominatimProvider(user_agent=settings.nominatim_user_agent)]
    if settings.google_maps_api_key:
        providers.append(GoogleMapsProvider(api_key=settings.google_maps_api_key))
    return CascadeGeocodingProvider(providers)


def get_geocoding_provider() -> CascadeGeocodingProvider:
    global _geocoding_provider
    if _geocoding_provider is None:
        _geocoding_provider = build_geocoding_provider()
    return _geocoding_provider


async def init_redis() -> None:
    global _redis_client
    _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    if _redis_client:
        await _redis_client.aclose()


def get_redis() -> aioredis.Redis:
    if _redis_client is None:
        raise RuntimeError("Redis not initialised. Call init_redis() first.")
    return _redis_client


async def require_bot_auth(x_bot_secret: Annotated[str | None, Header()] = None) -> None:
    if not x_bot_secret or not hmac.compare_digest(x_bot_secret, settings.bot_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


DBSession = Annotated[AsyncSession, Depends(get_session)]
BotAuth = Annotated[None, Depends(require_bot_auth)]
GeoProvider = Annotated[CascadeGeocodingProvider, Depends(get_geocoding_provider)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]
