"""FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.dependencies import close_redis, init_redis
from api.messaging.events import EventPublisher
from api.routers import discovery, preferences, profile, registration
from shared.db.session import close_db, init_db
from shared.storage.s3 import build_s3_client, ensure_bucket

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# `docker compose restart` does not wait on depends_on / health again; RabbitMQ can need
# tens of seconds to accept AMQP after the API container is already up.
_RABBITMQ_CONNECT_MAX_ATTEMPTS = 45
_RABBITMQ_CONNECT_RETRY_DELAY_S = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting API (env=%s)", settings.app_env)
    init_db(settings.database_url)
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
    await close_db()
    await close_redis()
    pub = getattr(app.state, "event_publisher", None)
    if isinstance(pub, EventPublisher):
        await pub.close()
    logger.info("API shutdown complete")


app = FastAPI(
    title="Dating Bot Profile API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(registration.router)
app.include_router(profile.router)
app.include_router(preferences.router)
app.include_router(discovery.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
