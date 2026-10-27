from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoldenQuery(BaseModel):
    """One validated JSONL record from a golden dataset."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=10_000)
    ground_truth: str = Field(min_length=1, max_length=50_000)
    reference_contexts: list[str] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reference_contexts")
    @classmethod
    def normalize_reference_contexts(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("reference_contexts cannot contain blank strings")
        return normalized


class DatasetImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    filename: str | None = Field(default=None, max_length=255)
    jsonl: str = Field(min_length=2)


class DatasetVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    content_hash: str
    source_filename: str | None
    item_count: int
    validation_summary: dict[str, Any]
    created_at: datetime


class DatasetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    latest_version: DatasetVersionSummary
    version_count: int


class DatasetItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    question: str
    ground_truth: str
    reference_contexts: list[str]
    item_metadata: dict[str, Any]


class DatasetDetail(DatasetSummary):
    version: DatasetVersionSummary
    items: list[DatasetItemResponse]


class DatasetImportResponse(BaseModel):
    dataset: DatasetSummary
    version: DatasetVersionSummary
    created_version: bool
