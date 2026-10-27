from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.schemas.dataset import (
    DatasetDetail,
    DatasetImportRequest,
    DatasetImportResponse,
    DatasetItemResponse,
    DatasetSummary,
    DatasetVersionSummary,
    GoldenQuery,
)
from app.storage.models import Dataset, DatasetItem, DatasetVersion


class DatasetValidationError(ValueError):
    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def _version_summary(version: DatasetVersion) -> DatasetVersionSummary:
    return DatasetVersionSummary.model_validate(version)


def _summary(dataset: Dataset) -> DatasetSummary:
    if not dataset.versions:
        raise DatasetValidationError("Dataset has no versions")
    return DatasetSummary(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        created_at=dataset.created_at,
        latest_version=_version_summary(dataset.versions[-1]),
        version_count=len(dataset.versions),
    )


def parse_jsonl(payload: str, *, settings: Settings) -> tuple[list[GoldenQuery], dict[str, Any]]:
    encoded = payload.encode("utf-8")
    if len(encoded) > settings.max_dataset_bytes:
        raise DatasetValidationError(
            f"Dataset exceeds the {settings.max_dataset_bytes} byte upload limit"
        )
    queries: list[GoldenQuery] = []
    errors: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if len(queries) >= settings.max_dataset_items:
            raise DatasetValidationError(
                f"Dataset exceeds the {settings.max_dataset_items} query limit"
            )
        try:
            raw = json.loads(stripped)
            queries.append(GoldenQuery.model_validate(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append({"line": line_number, "error": str(exc)[:500]})
            if len(errors) >= 25:
                break
    if errors:
        raise DatasetValidationError(f"{len(errors)} JSONL line(s) failed validation", errors)
    if not queries:
        raise DatasetValidationError("Dataset contains no queries")

    duplicate_count = sum(
        count - 1 for count in Counter(query.question for query in queries).values() if count > 1
    )
    summary = {
        "valid_queries": len(queries),
        "duplicate_questions": duplicate_count,
        "min_reference_contexts": min(len(query.reference_contexts) for query in queries),
        "mean_question_length": round(
            sum(len(query.question) for query in queries) / len(queries), 2
        ),
    }
    return queries, summary


def canonical_content_hash(queries: list[GoldenQuery]) -> str:
    canonical = [
        {
            "question": query.question,
            "ground_truth": query.ground_truth,
            "reference_contexts": query.reference_contexts,
            "metadata": query.metadata,
        }
        for query in queries
    ]
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def import_dataset(
    session: AsyncSession,
    settings: Settings,
    payload: DatasetImportRequest,
) -> DatasetImportResponse:
    queries, validation_summary = parse_jsonl(payload.jsonl, settings=settings)
    content_hash = canonical_content_hash(queries)

    dataset = await session.scalar(
        select(Dataset)
        .where(Dataset.name == payload.name)
        .options(selectinload(Dataset.versions).selectinload(DatasetVersion.items))
    )
    created_version = False
    if dataset is None:
        dataset = Dataset(name=payload.name, description=payload.description)
        session.add(dataset)
        await session.flush()
        version_number = 1
    else:
        for existing in dataset.versions:
            if existing.content_hash == content_hash:
                await session.commit()
                refreshed = await _load_dataset(session, dataset.id)
                return DatasetImportResponse(
                    dataset=_summary(refreshed),
                    version=_version_summary(existing),
                    created_version=False,
                )
        version_number = max(version.version_number for version in dataset.versions) + 1
        if payload.description is not None:
            dataset.description = payload.description

    version = DatasetVersion(
        dataset=dataset,
        version_number=version_number,
        content_hash=content_hash,
        source_filename=payload.filename,
        item_count=len(queries),
        validation_summary=validation_summary,
    )
    session.add(version)
    await session.flush()
    for ordinal, query in enumerate(queries):
        session.add(
            DatasetItem(
                dataset_version_id=version.id,
                ordinal=ordinal,
                question=query.question,
                ground_truth=query.ground_truth,
                reference_contexts=query.reference_contexts,
                item_metadata=query.metadata,
            )
        )
    await session.commit()
    created_version = True
    refreshed = await _load_dataset(session, dataset.id)
    return DatasetImportResponse(
        dataset=_summary(refreshed),
        version=_version_summary(version),
        created_version=created_version,
    )


async def _load_dataset(session: AsyncSession, dataset_id: uuid.UUID) -> Dataset:
    dataset = await session.scalar(
        select(Dataset)
        .where(Dataset.id == dataset_id)
        .options(selectinload(Dataset.versions).selectinload(DatasetVersion.items))
    )
    if dataset is None:
        raise DatasetValidationError("Dataset not found")
    return dataset


async def list_datasets(
    session: AsyncSession,
) -> list[DatasetSummary]:
    datasets = (
        await session.scalars(
            select(Dataset)
            .options(selectinload(Dataset.versions))
            .order_by(Dataset.created_at.desc())
        )
    ).all()
    return [_summary(dataset) for dataset in datasets]


async def get_dataset_detail(
    session: AsyncSession,
    dataset_id: uuid.UUID,
) -> DatasetDetail | None:
    dataset = await session.scalar(
        select(Dataset)
        .where(Dataset.id == dataset_id)
        .options(selectinload(Dataset.versions).selectinload(DatasetVersion.items))
    )
    if dataset is None:
        return None
    summary = _summary(dataset)
    latest = dataset.versions[-1]
    return DatasetDetail(
        **summary.model_dump(),
        version=_version_summary(latest),
        items=[
            DatasetItemResponse.model_validate(item)
            for item in sorted(latest.items, key=lambda item: item.ordinal)
        ],
    )


async def count_datasets(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Dataset)) or 0)
