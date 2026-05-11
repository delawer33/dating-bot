"""Shared async SQLAlchemy engine factory for worker processes."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from shared.config import SharedConfig


def create_async_engine_and_sessionmaker() -> tuple[
    AsyncEngine, async_sessionmaker[AsyncSession]
]:
    cfg = SharedConfig()
    engine = create_async_engine(
        cfg.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=cfg.database_pool_size,
        max_overflow=cfg.database_max_overflow,
        pool_recycle=cfg.database_pool_recycle,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory
