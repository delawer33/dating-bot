"""Alembic env: async migrations using asyncpg driver."""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from shared.config import SharedConfig
from shared.db.base import Base

# Import all models so Alembic's autogenerate sees them.
import shared.db.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Alembic uses sync URLs internally; we convert asyncpg → psycopg2 format only
# for offline mode. Online mode uses the asyncpg driver directly.
_settings = SharedConfig()

# Alembic needs a *sync*-compatible URL for offline mode; strip async driver.
_sync_url = _settings.database_url.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # Use the asyncpg URL from settings; override the placeholder in alembic.ini.
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _settings.database_url

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
