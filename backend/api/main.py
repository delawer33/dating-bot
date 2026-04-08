"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.dependencies import close_redis, init_redis
from api.routers import registration
from shared.db.session import close_db, init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting API (env=%s)", settings.app_env)
    init_db(settings.database_url)
    await init_redis()
    yield
    await close_db()
    await close_redis()
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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
