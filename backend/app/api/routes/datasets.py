from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import SessionDep, require_write_access
from app.core.config import get_settings
from app.schemas.dataset import (
    DatasetDetail,
    DatasetImportRequest,
    DatasetImportResponse,
    DatasetSummary,
)
from app.services.datasets import (
    DatasetValidationError,
    get_dataset_detail,
    import_dataset,
    list_datasets,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetSummary])
async def list_dataset_catalogue(session: SessionDep) -> list[DatasetSummary]:
    return await list_datasets(session)


@router.get("/sample", response_class=FileResponse)
async def download_sample_dataset() -> FileResponse:
    settings = get_settings()
    if not settings.sample_dataset_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample dataset is unavailable",
        )
    return FileResponse(
        settings.sample_dataset_path,
        media_type="application/x-ndjson",
        filename="evalforge-golden-dataset.jsonl",
    )


@router.post(
    "",
    response_model=DatasetImportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_access)],
)
async def import_dataset_endpoint(
    payload: DatasetImportRequest,
    session: SessionDep,
) -> DatasetImportResponse:
    try:
        return await import_dataset(session, get_settings(), payload)
    except DatasetValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc


@router.get("/{dataset_id}", response_model=DatasetDetail)
async def get_dataset_endpoint(
    dataset_id: uuid.UUID,
    session: SessionDep,
) -> DatasetDetail:
    dataset = await get_dataset_detail(session, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found",
        )
    return dataset
