from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.schemas.run import MetaResponse
from app.services.meta import build_meta

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaResponse)
async def get_meta(session: SessionDep) -> MetaResponse:
    return await build_meta(session, get_settings())
