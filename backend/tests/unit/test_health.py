from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import get_settings
from app.main import create_app
from app.storage.session import get_session


async def test_health_returns_version_and_environment(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "environment": get_settings().environment,
    }


async def test_root_health_is_available_for_render(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "EvalForge API"


async def test_readiness_checks_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


async def test_readiness_returns_503_when_database_is_unavailable() -> None:
    broken_session = AsyncMock(spec=AsyncSession)
    broken_session.execute.side_effect = SQLAlchemyError("database down")

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield broken_session

    application = create_app()
    application.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}


async def test_openapi_is_generated(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
    assert "/api/v1/health/ready" in response.json()["paths"]
