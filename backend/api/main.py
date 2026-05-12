"""FastAPI application entry point."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from api.config import settings
from api.dependencies import close_redis, init_redis
from api.messaging.events import EventPublisher
from api.metrics import (
    PrometheusMetricsMiddleware,
    metrics_response,
    observe_geocode_attempt,
)
from api.middleware.request_context import RequestContextMiddleware
from api.routers import discovery, preferences, profile, registration
from shared.db.session import close_db, init_db
from shared.geo import cascade as geo_cascade
from shared.logging_setup import configure_logging
from shared.storage.s3 import build_s3_client, ensure_bucket

configure_logging(
    service="api",
    log_level=settings.log_level,
    json_logs=settings.effective_log_json,
)
logger = logging.getLogger(__name__)

# `docker compose restart` does not wait on depends_on / health again; RabbitMQ can need
# tens of seconds to accept AMQP after the API container is already up.
_RABBITMQ_CONNECT_MAX_ATTEMPTS = 45
_RABBITMQ_CONNECT_RETRY_DELAY_S = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting API (env=%s)", settings.app_env)
    init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=settings.database_pool_recycle,
    )
    geo_cascade.set_geocode_metrics_hook(observe_geocode_attempt)
    s3_client = build_s3_client(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )
    for attempt in range(8):
        try:
            await asyncio.to_thread(ensure_bucket, s3_client, settings.s3_bucket)
            break
        except Exception:  # pragma: no cover — MinIO not ready
            if attempt == 7:
                raise
            await asyncio.sleep(0.5)

    app.state.s3_client = s3_client
    await init_redis()
    event_publisher = EventPublisher(settings.rabbitmq_url)
    for attempt in range(_RABBITMQ_CONNECT_MAX_ATTEMPTS):
        try:
            await event_publisher.connect()
            break
        except Exception as exc:  # pragma: no cover — broker not ready
            await event_publisher.close()
            last = attempt == _RABBITMQ_CONNECT_MAX_ATTEMPTS - 1
            if last:
                logger.exception(
                    "RabbitMQ connect failed after %s attempts",
                    attempt + 1,
                )
                raise
            logger.warning(
                "RabbitMQ connect attempt %s/%s failed (%s); retrying in %.1fs",
                attempt + 1,
                _RABBITMQ_CONNECT_MAX_ATTEMPTS,
                exc,
                _RABBITMQ_CONNECT_RETRY_DELAY_S,
            )
            await asyncio.sleep(_RABBITMQ_CONNECT_RETRY_DELAY_S)
    logger.info("Event publisher connected to RabbitMQ")
    app.state.event_publisher = event_publisher
    yield
    geo_cascade.set_geocode_metrics_hook(None)
    await close_db()
    await close_redis()
    pub = getattr(app.state, "event_publisher", None)
    if isinstance(pub, EventPublisher):
        await pub.close()
    logger.info("API shutdown complete")


def _mount_routes(application: FastAPI, *, metrics_enabled: bool) -> None:
    application.include_router(registration.router)
    application.include_router(profile.router)
    application.include_router(preferences.router)
    application.include_router(discovery.router)

    @application.get("/health")
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    if metrics_enabled:

        @application.get("/metrics")
        async def metrics() -> Response:
            return metrics_response()


def create_app(
    *,
    use_lifespan: bool = True,
    enable_metrics: bool | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    Tests set ``use_lifespan=False`` to skip broker/DB/S3 startup.
    ``enable_metrics=False`` omits ``/metrics`` and HTTP metrics middleware (optional).
    """
    kwargs: dict = {
        "title": "Dating Bot Profile API",
        "version": "0.1.0",
        "docs_url": None if settings.is_production else "/docs",
        "redoc_url": None if settings.is_production else "/redoc",
    }
    if use_lifespan:
        kwargs["lifespan"] = lifespan
    metrics_on = settings.metrics_enabled if enable_metrics is None else enable_metrics
    application = FastAPI(**kwargs)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestContextMiddleware)
    if metrics_on:
        application.add_middleware(PrometheusMetricsMiddleware)
    _mount_routes(application, metrics_enabled=metrics_on)
    return application


app = create_app(use_lifespan=True)
