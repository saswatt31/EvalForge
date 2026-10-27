from fastapi import APIRouter, HTTPException, status

from app import __version__
from app.api.deps import SessionDep
from app.core.config import get_settings
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import database_is_ready

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(version=__version__, environment=settings.environment)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"description": "A required dependency is unavailable"}},
)
async def readiness(session: SessionDep) -> ReadinessResponse:
    if not await database_is_ready(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        )
    return ReadinessResponse()
