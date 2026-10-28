from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    JudgeMode,
    JudgmentStatus,
    MetricName,
    QueryResultStatus,
    RunSource,
    RunStatus,
    TargetKind,
    TTFTSource,
)


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=5, ge=1, le=20)
    prompt_version: str = Field(default="reference-rag-v1", min_length=1, max_length=64)


class JudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judge_provider: Literal["groq", "ollama"] = "groq"


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    dataset_version_id: uuid.UUID
    target_kind: TargetKind = TargetKind.REFERENCE
    provider_name: str = Field(default="groq", min_length=1, max_length=100)
    model_name: str | None = Field(default=None, max_length=200)
    target_config: dict[str, Any] = Field(default_factory=dict)
    pipeline_config: PipelineConfig = Field(default_factory=PipelineConfig)
    judge_mode: JudgeMode = JudgeMode.MOCK
    judge_model: str = Field(default="mock-lexical-v1", min_length=1, max_length=200)
    judge_repeats: int = Field(default=1, ge=1, le=5)
    evaluator_config: JudgeConfig = Field(default_factory=JudgeConfig)
    warmup_count: int = Field(default=0, ge=0, le=3)
    baseline_run_id: uuid.UUID | None = None
    source: RunSource = RunSource.DASHBOARD
    git_sha: str | None = Field(default=None, max_length=40)
    git_branch: str | None = Field(default=None, max_length=255)
    pull_request_number: int | None = Field(default=None, ge=1)

    @field_validator("git_sha")
    @classmethod
    def validate_git_sha(cls, value: str | None) -> str | None:
        if value is not None and not all(character in "0123456789abcdef" for character in value):
            raise ValueError("git_sha must be a lowercase hexadecimal commit SHA")
        return value

    @model_validator(mode="after")
    def validate_target(self) -> RunCreate:
        if self.target_kind is TargetKind.HTTP:
            url = self.target_config.get("url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                raise ValueError("HTTP targets require target_config.url")
            headers = self.target_config.get("headers", {})
            if not isinstance(headers, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
            ):
                raise ValueError("target_config.headers must be a string dictionary")
        elif self.provider_name not in {"groq", "ollama", "mock"}:
            raise ValueError("Reference targets support groq, ollama, or mock providers")
        return self


class MetricAggregate(BaseModel):
    mean: float | None
    judged_queries: int
    total_samples: int
    failed_samples: int


class LatencyAggregate(BaseModel):
    p50_ms: float | None
    p95_ms: float | None
    mean_ms: float | None
    ttft_p50_ms: float | None
    ttft_p95_ms: float | None
    measured_ttft_count: int
    target_reported_ttft_count: int
    demo_ttft_count: int
    mean_tokens_per_second: float | None


class RunMetrics(BaseModel):
    context_recall: MetricAggregate
    faithfulness: MetricAggregate
    answer_relevance: MetricAggregate
    hallucination_rate: MetricAggregate
    latency: LatencyAggregate
    success_rate: float | None
    cache_hits: int
    cache_misses: int


class RunSummary(BaseModel):
    id: uuid.UUID
    name: str
    status: RunStatus
    source: RunSource
    target_kind: TargetKind
    provider_name: str
    model_name: str | None
    target_config: dict[str, Any]
    pipeline_config: dict[str, Any]
    judge_mode: JudgeMode
    judge_model: str
    judge_repeats: int
    warmup_count: int
    config_hash: str
    dataset_version_id: uuid.UUID
    baseline_run_id: uuid.UUID | None
    total_queries: int
    completed_queries: int
    failed_queries: int
    error_message: str | None
    git_sha: str | None
    git_branch: str | None
    pull_request_number: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    metrics: RunMetrics


class RunPage(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


class MetricScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    metric_name: MetricName
    sample_index: int
    status: JudgmentStatus
    score: float | None
    reason: str | None
    evaluator: str
    judge_model: str
    prompt_version: str
    judge_cached: bool
    error_message: str | None
    details: dict[str, Any]


class QueryResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: QueryResultStatus
    question: str
    ground_truth: str
    answer: str | None
    contexts: list[str]
    ttft_ms: float | None
    ttft_source: TTFTSource | None
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    tokens_per_second: float | None
    error_message: str | None
    metrics: list[MetricScoreResponse]


class QueryResultPage(BaseModel):
    items: list[QueryResultResponse]
    total: int
    limit: int
    offset: int


class RunStatusResponse(BaseModel):
    id: uuid.UUID
    status: RunStatus
    completed_queries: int
    failed_queries: int
    total_queries: int


class CompareRow(BaseModel):
    metric: str
    baseline: float | None
    candidate: float | None
    delta: float | None
    relative_delta: float | None


class CompareResponse(BaseModel):
    baseline: RunSummary
    candidate: RunSummary
    rows: list[CompareRow]


class LiveRunPolicy(BaseModel):
    enabled: bool
    max_queries_per_run: int
    daily_run_cap: int | None
    per_ip_runs_per_window: int | None
    window_seconds: int | None


class MetaResponse(BaseModel):
    demo_mode: bool
    write_protected: bool
    database_ready: bool
    target_kinds: list[str]
    providers: list[dict[str, Any]]
    judge_modes: list[str]
    max_dataset_bytes: int
    max_dataset_items: int
    max_result_page_size: int
    sample_dataset_available: bool
    live_runs: LiveRunPolicy
