import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.storage.session import get_session
from app.workers.manager import RunManager

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_run_manager(request: Request) -> RunManager | None:
    return getattr(request.app.state, "run_manager", None)


RunManagerDep = Annotated[RunManager | None, Depends(get_run_manager)]


async def require_write_access(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    if settings.demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo mode is read-only",
        )
    expected = settings.write_api_token
    if expected is None:
        return
    supplied = x_api_key
    if supplied is None and authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ").strip()
    if supplied is None or not hmac.compare_digest(supplied, expected.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid write API token is required",
        )


WriteAccessDep = Annotated[None, Depends(require_write_access)]
