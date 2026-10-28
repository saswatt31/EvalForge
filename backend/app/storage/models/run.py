from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    JudgeMode,
    JudgmentStatus,
    QueryResultStatus,
    RunSource,
    RunStatus,
    TargetKind,
    TTFTSource,
)
from app.storage.base import Base, TimestampMixin, new_uuid, utc_now
from app.storage.models.dataset import DatasetItem, DatasetVersion
from app.storage.types import string_enum


class Run(Base, TimestampMixin):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("total_queries >= 0", name="total_queries_nonnegative"),
        CheckConstraint("completed_queries >= 0", name="completed_queries_nonnegative"),
        CheckConstraint("failed_queries >= 0", name="failed_queries_nonnegative"),
        CheckConstraint(
            "completed_queries + failed_queries <= total_queries",
            name="progress_within_total",
        ),
        CheckConstraint("judge_repeats >= 1", name="judge_repeats_positive"),
        CheckConstraint("warmup_count >= 0", name="warmup_count_nonnegative"),
        Index("ix_runs_status_created_at", "status", "created_at"),
        Index("ix_runs_created_at", "created_at"),
        Index("ix_runs_client_ip_hash_created_at", "client_ip_hash", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        string_enum(RunStatus),
        nullable=False,
        default=RunStatus.QUEUED,
    )
    source: Mapped[RunSource] = mapped_column(string_enum(RunSource), nullable=False)
    target_kind: Mapped[TargetKind] = mapped_column(string_enum(TargetKind), nullable=False)

    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    pipeline_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    judge_mode: Mapped[JudgeMode] = mapped_column(string_enum(JudgeMode), nullable=False)
    judge_model: Mapped[str] = mapped_column(String(200), nullable=False)
    judge_repeats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    warmup_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluator_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    git_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pull_request_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # SHA-256 of the caller's IP plus a deployment salt. Used only for the live-run rate limit.
    client_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    total_queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    dataset_version: Mapped[DatasetVersion] = relationship()
    query_results: Mapped[list[QueryResult]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class QueryResult(Base, TimestampMixin):
    __tablename__ = "query_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "dataset_item_id",
            name="uq_query_results_run_item",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint("ttft_ms IS NULL OR ttft_ms >= 0", name="ttft_nonnegative"),
        CheckConstraint(
            "(ttft_ms IS NULL) = (ttft_source IS NULL)",
            name="ttft_provenance_consistency",
        ),
        CheckConstraint(
            "ttft_ms IS NULL OR latency_ms IS NULL OR ttft_ms <= latency_ms",
            name="ttft_not_after_total",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="output_tokens_nonnegative",
        ),
        CheckConstraint(
            "tokens_per_second IS NULL OR tokens_per_second >= 0",
            name="tokens_per_second_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[QueryResultStatus] = mapped_column(
        string_enum(QueryResultStatus),
        nullable=False,
    )
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    contexts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    ttft_source: Mapped[TTFTSource | None] = mapped_column(
        string_enum(TTFTSource),
        nullable=True,
    )
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[Run] = relationship(back_populates="query_results")
    dataset_item: Mapped[DatasetItem] = relationship()
    metric_scores: Mapped[list[MetricScore]] = relationship(
        back_populates="query_result",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MetricScore(Base, TimestampMixin):
    __tablename__ = "metric_scores"
    __table_args__ = (
        UniqueConstraint(
            "query_result_id",
            "metric_name",
            "sample_index",
            name="uq_metric_scores_result_metric_sample",
        ),
        CheckConstraint("sample_index >= 0", name="sample_index_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    query_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("query_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[JudgmentStatus] = mapped_column(
        string_enum(JudgmentStatus),
        nullable=False,
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluator: Mapped[str] = mapped_column(String(64), nullable=False)
    judge_model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    judge_cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    query_result: Mapped[QueryResult] = relationship(back_populates="metric_scores")
