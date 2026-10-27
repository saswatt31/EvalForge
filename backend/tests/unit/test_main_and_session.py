from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.main as main_module
import app.storage.session as session_module
from app.core.config import Settings
from app.main import lifespan
from app.storage.session import configure_sqlite, get_session


async def test_lifespan_starts_and_stops_manager(
    monkeypatch: Any,
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    test_settings.demo_mode = False
    monkeypatch.setattr(main_module, "get_settings", lambda: test_settings)
    monkeypatch.setattr(main_module, "SessionFactory", session_factory)
    application = FastAPI()

    async with lifespan(application):
        manager = application.state.run_manager
        assert manager._task is not None

    assert manager._task is None


async def test_get_session_yields_usable_session(
    monkeypatch: Any,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setattr(session_module, "SessionFactory", session_factory)
    async for session in get_session():
        value = await session.scalar(text("select 1"))
        assert value == 1


def test_sqlite_connection_configuration(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    database = tmp_path / "configured.db"
    monkeypatch.setattr(
        session_module,
        "settings",
        SimpleNamespace(database_url=f"sqlite+aiosqlite:///{database.as_posix()}"),
    )
    connection = sqlite3.connect(database)
    configure_sqlite(connection, None)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    connection.close()

    monkeypatch.setattr(
        session_module,
        "settings",
        SimpleNamespace(database_url="postgresql+asyncpg://example"),
    )
    connection = sqlite3.connect(":memory:")
    configure_sqlite(connection, None)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (0,)
    connection.close()
