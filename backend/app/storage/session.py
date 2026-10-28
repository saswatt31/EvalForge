from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings

settings = get_settings()


def engine_options(settings: Settings) -> dict[str, Any]:
    """Return engine options that work for SQLite locally and hosted Postgres in production."""

    options: dict[str, Any] = {"pool_pre_ping": True}
    if settings.database_url.startswith("postgresql+asyncpg"):
        options.update(
            {
                "pool_size": 5,
                "max_overflow": 5,
                "pool_recycle": 1_800,
            }
        )
        if settings.database_ssl is not False:
            options["connect_args"] = {"ssl": True}
    return options


engine = create_async_engine(settings.database_url, **engine_options(settings))
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def configure_sqlite(dbapi_connection: Any, _connection_record: Any) -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    if ":memory:" not in settings.database_url:
        cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
