"""Prometheus metrics for the HTTP API (HTTP, discovery, events, pool, geocode)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Buckets tuned for a small JSON API (seconds).
_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Wall time for HTTP requests handled by this process (seconds).",
    ("method", "path"),
    buckets=_HTTP_BUCKETS,
)

http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests handled by this process.",
    ("method", "path", "status"),
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently being handled (excludes GET /metrics).",
)

event_publish_total = Counter(
    "event_publish_total",
    "RabbitMQ domain event publish attempts (dating.events).",
    ("event_type", "result"),
)

bot_auth_failures_total = Counter(
    "bot_auth_failures_total",
    "Rejected X-Bot-Secret authentications (401).",
)

geocode_reverse_attempts_total = Counter(
    "geocode_reverse_attempts_total",
    "Reverse geocode attempts per provider in the cascade.",
    ("provider", "outcome"),
)

discovery_actions_total = Counter(
    "discovery_actions_total",
    "Discovery outcomes (committed writes and feed shape).",
    ("operation", "outcome"),
)

db_pool_connections_checked_out = Gauge(
    "db_pool_connections_checked_out",
    "SQLAlchemy async pool connections currently checked out.",
)

db_pool_connections_size = Gauge(
    "db_pool_connections_size",
    "Connections currently tracked by the pool (checked in + out + overflow).",
)

db_pool_overflow = Gauge(
    "db_pool_overflow",
    "Overflow connections beyond pool_size (SQLAlchemy pool).",
)


def route_template(request: Request) -> str:
    """Stable route label: OpenAPI path template when matched, else ``unmatched``.

    Call this only after the request has been routed (e.g. after ``call_next`` in
    middleware): ``scope["route"]`` is populated by Starlette only then.
    """
    route = request.scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            return path
    return "unmatched"


def observe_geocode_attempt(provider_name: str, outcome: str) -> None:
    """Hook for ``shared.geo.cascade`` (registered from API lifespan)."""
    geocode_reverse_attempts_total.labels(provider=provider_name, outcome=outcome).inc()


def record_event_publish(event_type: str, result: str) -> None:
    event_publish_total.labels(event_type=event_type, result=result).inc()


def record_discovery_action(operation: str, outcome: str) -> None:
    discovery_actions_total.labels(operation=operation, outcome=outcome).inc()


def record_bot_auth_failure() -> None:
    bot_auth_failures_total.inc()


def _refresh_db_pool_gauges() -> None:
    from shared.db.session import db_pool_stats

    stats = db_pool_stats()
    if stats is None:
        return
    db_pool_connections_checked_out.set(stats["checked_out"])
    db_pool_connections_size.set(stats["size"])
    db_pool_overflow.set(stats["overflow"])


def metrics_response() -> Response:
    """Prometheus text exposition for the default registry."""
    _refresh_db_pool_gauges()
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Record latency and status; skips ``GET /metrics`` to avoid scrape noise."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == "GET" and request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        http_requests_in_progress.inc()
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                elapsed = time.perf_counter() - start
                path_tpl = route_template(request)
                http_request_duration_seconds.labels(method=method, path=path_tpl).observe(elapsed)
                http_requests_total.labels(method=method, path=path_tpl, status="500").inc()
                raise

            elapsed = time.perf_counter() - start
            path_tpl = route_template(request)
            status = str(response.status_code)
            http_request_duration_seconds.labels(method=method, path=path_tpl).observe(elapsed)
            http_requests_total.labels(method=method, path=path_tpl, status=status).inc()
            return response
        finally:
            http_requests_in_progress.dec()
