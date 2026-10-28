from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import RunManagerDep, SessionDep, require_write_access
from app.core.config import get_settings
from app.core.enums import RunStatus
from app.schemas.run import (
    CompareResponse,
    QueryResultPage,
    RunCreate,
    RunPage,
    RunStatusResponse,
    RunSummary,
)
from app.services.live_runs import (
    LiveRunLimitError,
    client_ip_from_request,
    reserve_live_run_slot,
)
from app.services.runs import (
    RunNotFoundError,
    RunServiceError,
    cancel_run,
    compare_runs,
    create_run,
    get_run,
    get_run_results,
    get_run_summary,
    list_runs,
)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=RunPage)
async def list_runs_endpoint(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    dataset_version_id: uuid.UUID | None = None,
) -> RunPage:
    return await list_runs(
        session,
        limit=limit,
        offset=offset,
        status=run_status,
        dataset_version_id=dataset_version_id,
    )


@router.post(
    "",
    response_model=RunSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_access)],
)
async def create_run_endpoint(
    payload: RunCreate,
    request: Request,
    session: SessionDep,
    manager: RunManagerDep,
) -> RunSummary:
    settings = get_settings()
    try:
        async with reserve_live_run_slot(
            session,
            settings,
            client_ip_from_request(request),
        ) as client_ip_hash:
            run = await create_run(
                session,
                settings,
                payload,
                client_ip_hash=client_ip_hash,
                max_queries=settings.live_run_max_queries if settings.live_run_protection else None,
            )
    except LiveRunLimitError as exc:
        limit = exc.limit
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "live_runs_paused",
                "reason": limit.reason,
                "message": limit.message,
                "limit": limit.limit,
                "retry_after_seconds": limit.retry_after_seconds,
            },
            headers={"Retry-After": str(limit.retry_after_seconds)},
        ) from exc
    except RunServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if manager is not None:
        await manager.enqueue(run.id)
    return await get_run_summary(session, run)


@router.get("/compare", response_model=CompareResponse)
async def compare_runs_endpoint(
    session: SessionDep,
    baseline_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> CompareResponse:
    try:
        return await compare_runs(
            session,
            baseline_id=baseline_id,
            candidate_id=candidate_id,
        )
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/{run_id}", response_model=RunSummary)
async def get_run_endpoint(run_id: uuid.UUID, session: SessionDep) -> RunSummary:
    run = await get_run(session, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )
    return await get_run_summary(session, run)


@router.get("/{run_id}/status", response_model=RunStatusResponse)
async def get_run_status_endpoint(
    run_id: uuid.UUID,
    session: SessionDep,
) -> RunStatusResponse:
    run = await get_run(session, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )
    return RunStatusResponse(
        id=run.id,
        status=run.status,
        completed_queries=run.completed_queries,
        failed_queries=run.failed_queries,
        total_queries=run.total_queries,
    )


@router.get("/{run_id}/results", response_model=QueryResultPage)
async def get_run_results_endpoint(
    run_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QueryResultPage:
    page = await get_run_results(session, run_id, limit=limit, offset=offset)
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )
    return page


@router.post(
    "/{run_id}/cancel",
    response_model=RunStatusResponse,
    dependencies=[Depends(require_write_access)],
)
async def cancel_run_endpoint(
    run_id: uuid.UUID,
    session: SessionDep,
) -> RunStatusResponse:
    try:
        run = await cancel_run(session, run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RunServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return RunStatusResponse(
        id=run.id,
        status=run.status,
        completed_queries=run.completed_queries,
        failed_queries=run.failed_queries,
        total_queries=run.total_queries,
    )
