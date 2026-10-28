from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.enums import RunStatus
from app.schemas.run import (
    CompareResponse,
    CompareRow,
    MetricScoreResponse,
    QueryResultPage,
    QueryResultResponse,
    RunCreate,
    RunMetrics,
    RunPage,
    RunSummary,
)
from app.services.metrics import aggregate_run_metrics
from app.storage.base import utc_now
from app.storage.models import (
    DatasetItem,
    DatasetVersion,
    MetricScore,
    QueryResult,
    Run,
)


class RunServiceError(ValueError):
    pass


class RunNotFoundError(RunServiceError):
    pass


def canonical_run_hash(payload: RunCreate) -> str:
    canonical = {
        "dataset_version_id": str(payload.dataset_version_id),
        "target_kind": payload.target_kind.value,
        "provider_name": payload.provider_name,
        "model_name": payload.model_name,
        "target_config": payload.target_config,
        "pipeline_config": payload.pipeline_config.model_dump(),
        "judge_mode": payload.judge_mode.value,
        "judge_model": payload.judge_model,
        "judge_repeats": payload.judge_repeats,
        "evaluator_config": payload.evaluator_config.model_dump(),
        "warmup_count": payload.warmup_count,
    }
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def default_run_name(payload: RunCreate) -> str:
    provider = payload.model_name or payload.provider_name
    return f"{provider} - {payload.target_kind.value} - k={payload.pipeline_config.top_k}"


async def create_run(
    session: AsyncSession,
    settings: Settings,
    payload: RunCreate,
    *,
    client_ip_hash: str | None = None,
    max_queries: int | None = None,
) -> Run:
    version = await session.get(DatasetVersion, payload.dataset_version_id)
    if version is None:
        raise RunServiceError("Dataset version not found")
    if payload.baseline_run_id is not None:
        baseline = await session.get(Run, payload.baseline_run_id)
        if baseline is None:
            raise RunServiceError("Baseline run not found")
    if (
        payload.judge_mode.value == "llm"
        and payload.evaluator_config.judge_provider == "groq"
        and settings.groq_api_key is None
    ):
        raise RunServiceError("LLM judging with Groq requires EVALFORGE_GROQ_API_KEY")

    total_queries = version.item_count
    if max_queries is not None:
        total_queries = min(total_queries, max_queries)

    run = Run(
        dataset_version_id=payload.dataset_version_id,
        name=payload.name or default_run_name(payload),
        status=RunStatus.QUEUED,
        source=payload.source,
        target_kind=payload.target_kind,
        provider_name=payload.provider_name,
        model_name=payload.model_name,
        target_config=payload.target_config,
        pipeline_config=payload.pipeline_config.model_dump(),
        judge_mode=payload.judge_mode,
        judge_model=payload.judge_model,
        judge_repeats=payload.judge_repeats,
        warmup_count=payload.warmup_count,
        evaluator_config=payload.evaluator_config.model_dump(),
        config_hash=canonical_run_hash(payload),
        baseline_run_id=payload.baseline_run_id,
        git_sha=payload.git_sha,
        git_branch=payload.git_branch,
        pull_request_number=payload.pull_request_number,
        client_ip_hash=client_ip_hash,
        total_queries=total_queries,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


def sanitize_target_config(config: dict[str, Any]) -> dict[str, Any]:
    displayed = {key: value for key, value in config.items() if key != "headers"}
    if config.get("headers"):
        displayed["header_names"] = sorted(str(key) for key in config["headers"])
    return displayed


def run_summary(run: Run, *, metrics: RunMetrics) -> RunSummary:
    return RunSummary(
        id=run.id,
        name=run.name,
        status=run.status,
        source=run.source,
        target_kind=run.target_kind,
        provider_name=run.provider_name,
        model_name=run.model_name,
        target_config=sanitize_target_config(run.target_config),
        pipeline_config=run.pipeline_config,
        judge_mode=run.judge_mode,
        judge_model=run.judge_model,
        judge_repeats=run.judge_repeats,
        warmup_count=run.warmup_count,
        config_hash=run.config_hash,
        dataset_version_id=run.dataset_version_id,
        baseline_run_id=run.baseline_run_id,
        total_queries=run.total_queries,
        completed_queries=run.completed_queries,
        failed_queries=run.failed_queries,
        error_message=run.error_message,
        git_sha=run.git_sha,
        git_branch=run.git_branch,
        pull_request_number=run.pull_request_number,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        metrics=metrics,
    )


async def get_run_metrics(session: AsyncSession, run: Run) -> RunMetrics:
    results = (await session.scalars(select(QueryResult).where(QueryResult.run_id == run.id))).all()
    scores = (
        await session.scalars(
            select(MetricScore)
            .join(QueryResult, MetricScore.query_result_id == QueryResult.id)
            .where(QueryResult.run_id == run.id)
        )
    ).all()
    return aggregate_run_metrics(
        total_queries=run.total_queries,
        query_results=list(results),
        scores=list(scores),
    )


async def get_run_summary(session: AsyncSession, run: Run) -> RunSummary:
    return run_summary(run, metrics=await get_run_metrics(session, run))


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> Run | None:
    return await session.get(Run, run_id)


async def list_runs(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: RunStatus | None = None,
    dataset_version_id: uuid.UUID | None = None,
) -> RunPage:
    filters = []
    if status is not None:
        filters.append(Run.status == status)
    if dataset_version_id is not None:
        filters.append(Run.dataset_version_id == dataset_version_id)
    total = int(await session.scalar(select(func.count()).select_from(Run).where(*filters)) or 0)
    runs = (
        await session.scalars(
            select(Run).where(*filters).order_by(Run.created_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    items = [await get_run_summary(session, run) for run in runs]
    return RunPage(items=items, total=total, limit=limit, offset=offset)


async def cancel_run(session: AsyncSession, run_id: uuid.UUID) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise RunNotFoundError("Run not found")
    if run.status in {
        RunStatus.SUCCEEDED,
        RunStatus.PARTIAL,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }:
        raise RunServiceError("Run is already complete")
    run.status = RunStatus.CANCELLED
    run.finished_at = utc_now()
    await session.commit()
    await session.refresh(run)
    return run


async def get_run_results(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> QueryResultPage | None:
    run = await session.get(Run, run_id)
    if run is None:
        return None
    total = int(
        await session.scalar(
            select(func.count()).select_from(QueryResult).where(QueryResult.run_id == run_id)
        )
        or 0
    )
    results = (
        await session.scalars(
            select(QueryResult)
            .join(DatasetItem, QueryResult.dataset_item_id == DatasetItem.id)
            .where(QueryResult.run_id == run_id)
            .options(
                selectinload(QueryResult.dataset_item),
                selectinload(QueryResult.metric_scores),
            )
            .order_by(DatasetItem.ordinal, QueryResult.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items: list[QueryResultResponse] = []
    for result in results:
        scores = sorted(
            result.metric_scores,
            key=lambda score: (score.metric_name, score.sample_index),
        )
        items.append(
            QueryResultResponse(
                id=result.id,
                status=result.status,
                question=result.dataset_item.question,
                ground_truth=result.dataset_item.ground_truth,
                answer=result.answer,
                contexts=result.contexts,
                ttft_ms=result.ttft_ms,
                ttft_source=result.ttft_source,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                tokens_per_second=result.tokens_per_second,
                error_message=result.error_message,
                metrics=[MetricScoreResponse.model_validate(score) for score in scores],
            )
        )
    return QueryResultPage(items=items, total=total, limit=limit, offset=offset)


def _quality_value(run: RunSummary, metric: str) -> float | None:
    if metric == "context_recall":
        return run.metrics.context_recall.mean
    if metric == "faithfulness":
        return run.metrics.faithfulness.mean
    if metric == "answer_relevance":
        return run.metrics.answer_relevance.mean
    if metric == "hallucination_rate":
        return run.metrics.hallucination_rate.mean
    if metric == "success_rate":
        return run.metrics.success_rate
    if metric == "latency_p50_ms":
        return run.metrics.latency.p50_ms
    if metric == "latency_p95_ms":
        return run.metrics.latency.p95_ms
    if metric == "ttft_p50_ms":
        return run.metrics.latency.ttft_p50_ms
    if metric == "ttft_p95_ms":
        return run.metrics.latency.ttft_p95_ms
    if metric == "tokens_per_second":
        return run.metrics.latency.mean_tokens_per_second
    return None


async def compare_runs(
    session: AsyncSession,
    *,
    baseline_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> CompareResponse:
    baseline_run = await session.get(Run, baseline_id)
    candidate_run = await session.get(Run, candidate_id)
    if baseline_run is None or candidate_run is None:
        raise RunNotFoundError("One or both runs were not found")
    baseline = await get_run_summary(session, baseline_run)
    candidate = await get_run_summary(session, candidate_run)
    metrics = [
        "context_recall",
        "faithfulness",
        "answer_relevance",
        "hallucination_rate",
        "success_rate",
        "latency_p50_ms",
        "latency_p95_ms",
        "ttft_p50_ms",
        "ttft_p95_ms",
        "tokens_per_second",
    ]
    rows: list[CompareRow] = []
    for metric in metrics:
        baseline_value = _quality_value(baseline, metric)
        candidate_value = _quality_value(candidate, metric)
        delta = (
            candidate_value - baseline_value
            if baseline_value is not None and candidate_value is not None
            else None
        )
        relative = None
        if delta is not None and baseline_value is not None and baseline_value != 0:
            relative = delta / baseline_value
        rows.append(
            CompareRow(
                metric=metric,
                baseline=baseline_value,
                candidate=candidate_value,
                delta=round(delta, 6) if delta is not None else None,
                relative_delta=round(relative, 6) if relative is not None else None,
            )
        )
    return CompareResponse(baseline=baseline, candidate=candidate, rows=rows)


async def queued_run_ids(session: AsyncSession) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(Run.id).where(Run.status == RunStatus.QUEUED).order_by(Run.created_at)
            )
        ).all()
    )
