from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_factory = None


def init_db(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_recycle: int = 1800,
) -> None:
    global _engine, _session_factory
    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("DB not initialised. Call init_db() first.")
    async with _session_factory() as session:
        yield session


async def close_db() -> None:
    if _engine:
        await _engine.dispose()


def db_pool_stats() -> dict[str, int] | None:
    """Snapshot of the async SQLAlchemy pool for metrics (None if DB not initialised)."""
    if _engine is None:
        return None
    pool = _engine.pool
    try:
        return {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception:
        return None
