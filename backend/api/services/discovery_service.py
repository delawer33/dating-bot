"""Discovery queue (Redis), candidate ranking, and interactions — public API."""

from __future__ import annotations

from api.services.discovery.constants import (
    DISCOVERY_QUEUE_KEY,
    DISCOVERY_TTL_SEC,
    PREFETCH_BATCH,
    RANK_FETCH_CAP,
)
from api.services.discovery.interactions import (
    build_profile_out,
    get_next_profile,
    list_incoming_likes,
    list_incoming_likes_inbox,
    record_like,
    record_skip,
)
from api.services.discovery.queue import invalidate_discovery_queue
from shared.geo.distance import haversine_km

__all__ = [
    "DISCOVERY_QUEUE_KEY",
    "DISCOVERY_TTL_SEC",
    "PREFETCH_BATCH",
    "RANK_FETCH_CAP",
    "build_profile_out",
    "get_next_profile",
    "haversine_km",
    "invalidate_discovery_queue",
    "list_incoming_likes",
    "list_incoming_likes_inbox",
    "record_like",
    "record_skip",
]
