"""Shared async SQLAlchemy engine factory for worker processes."""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def get_database_url() -> str:
    return os.environ["DATABASE_URL"]


def create_async_engine_and_sessionmaker() -> tuple[
    AsyncEngine, async_sessionmaker[AsyncSession]
]:
    engine = create_async_engine(get_database_url(), echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory
