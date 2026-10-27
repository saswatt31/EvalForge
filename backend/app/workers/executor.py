from __future__ import annotations

import asyncio
import logging
import statistics
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.base import RAGTarget
from app.adapters.factory import build_target
from app.core.config import Settings
from app.core.enums import (
    JudgmentStatus,
    MetricName,
    QueryResultStatus,
    RunStatus,
)
from app.evaluators import build_evaluator
from app.evaluators.base import EvaluationInput, Evaluator
from app.evaluators.cache import evaluate_with_cache
from app.storage.base import utc_now
from app.storage.models import DatasetItem, MetricScore, QueryResult, Run

logger = logging.getLogger(__name__)

DIRECT_METRICS = (
    MetricName.CONTEXT_RECALL,
    MetricName.FAITHFULNESS,
    MetricName.ANSWER_RELEVANCE,
)


class RunExecutor:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def execute(self, run_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                logger.warning("Run %s disappeared before execution", run_id)
                return
            if run.status is not RunStatus.QUEUED:
                return
            run.status = RunStatus.RUNNING
            run.started_at = utc_now()
            run.finished_at = None
            run.error_message = None
            await session.commit()
            items = list(
                (
                    await session.scalars(
                        select(DatasetItem)
                        .where(DatasetItem.dataset_version_id == run.dataset_version_id)
                        .order_by(DatasetItem.ordinal)
                    )
                ).all()
            )

        try:
            target, evaluator = await self._build_runtime(run)
        except Exception as exc:
            logger.exception("Failed to initialize run %s", run_id)
            await self._mark_failed(run_id, f"Run initialization failed: {exc}")
            return

        try:
            await self._run_items(run_id, items, target, evaluator)
        except asyncio.CancelledError:
            logger.info("Run %s interrupted by shutdown", run_id)
            raise
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            await self._mark_failed(run_id, f"Run execution failed: {exc}")
        finally:
            try:
                await target.aclose()
            finally:
                await evaluator.aclose()

    async def _build_runtime(self, run: Run) -> tuple[RAGTarget, Evaluator]:
        target = build_target(
            self._settings,
            target_kind=run.target_kind.value,
            provider_name=run.provider_name,
            model_name=run.model_name,
            target_config=run.target_config,
            pipeline_config=run.pipeline_config,
        )
        try:
            evaluator = build_evaluator(
                self._settings,
                judge_mode=run.judge_mode,
                judge_model=run.judge_model,
                evaluator_config=run.evaluator_config,
            )
        except Exception:
            await target.aclose()
            raise
        return target, evaluator

    async def _run_items(
        self,
        run_id: uuid.UUID,
        items: list[DatasetItem],
        target: RAGTarget,
        evaluator: Evaluator,
    ) -> None:
        async with self._session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None or await self._is_cancelled(session, run_id):
                return

            for item in items[: run.warmup_count]:
                await self._with_request_timeout(
                    target.query,
                    item.question,
                    self._settings.request_timeout_seconds,
                )

            for item in items:
                await session.refresh(run)
                if await self._is_cancelled(session, run_id):
                    break
                await self._execute_item(
                    session,
                    run,
                    item,
                    target,
                    evaluator,
                    self._settings.request_timeout_seconds,
                )

            await session.refresh(run)
            if await self._is_cancelled(session, run_id):
                return
            if run.completed_queries + run.failed_queries < run.total_queries:
                run.status = RunStatus.CANCELLED
            elif run.failed_queries == run.total_queries:
                run.status = RunStatus.FAILED
            elif run.failed_queries > 0:
                run.status = RunStatus.PARTIAL
            else:
                run.status = RunStatus.SUCCEEDED
            run.finished_at = utc_now()
            await session.commit()

    async def _execute_item(
        self,
        session: AsyncSession,
        run: Run,
        item: DatasetItem,
        target: RAGTarget,
        evaluator: Evaluator,
        timeout_seconds: float,
    ) -> None:
        try:
            response = await self._with_request_timeout(
                target.query,
                item.question,
                timeout_seconds,
            )
        except Exception as exc:
            result = QueryResult(
                run_id=run.id,
                dataset_item_id=item.id,
                status=QueryResultStatus.FAILED,
                contexts=[],
                error_message=str(exc)[:2000],
            )
            session.add(result)
            run.failed_queries += 1
            await session.commit()
            return

        result = QueryResult(
            run_id=run.id,
            dataset_item_id=item.id,
            status=QueryResultStatus.SUCCEEDED,
            answer=response.answer,
            contexts=response.contexts,
            ttft_ms=response.ttft_ms,
            ttft_source=response.ttft_source,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            tokens_per_second=response.tokens_per_second,
        )
        session.add(result)
        await session.flush()

        payload = EvaluationInput(
            question=item.question,
            answer=response.answer,
            contexts=response.contexts,
            ground_truth=item.ground_truth,
        )
        faithfulness_scores: list[float] = []
        for metric in DIRECT_METRICS:
            for sample_index in range(run.judge_repeats):
                await self._judge_metric(
                    session,
                    run,
                    result,
                    evaluator,
                    payload,
                    metric,
                    sample_index,
                    faithfulness_scores,
                )
        self._add_hallucination_score(session, run, evaluator, result, faithfulness_scores)
        run.completed_queries += 1
        await session.commit()

    async def _judge_metric(
        self,
        session: AsyncSession,
        run: Run,
        result: QueryResult,
        evaluator: Evaluator,
        payload: EvaluationInput,
        metric: MetricName,
        sample_index: int,
        faithfulness_scores: list[float],
    ) -> None:
        try:
            judged = await evaluate_with_cache(
                session,
                evaluator=evaluator,
                judge_model=run.judge_model,
                metric=metric,
                sample_index=sample_index,
                payload=payload,
            )
        except Exception as exc:
            logger.warning(
                "Judge failed for run %s metric %s sample %d: %s",
                run.id,
                metric.value,
                sample_index,
                exc,
            )
            session.add(
                MetricScore(
                    query_result_id=result.id,
                    metric_name=metric.value,
                    sample_index=sample_index,
                    status=JudgmentStatus.FAILED,
                    score=None,
                    reason=None,
                    evaluator=evaluator.name,
                    judge_model=run.judge_model,
                    prompt_version=evaluator.prompt_version,
                    judge_cached=False,
                    error_message=str(exc)[:2000],
                    details={},
                )
            )
            return

        if metric is MetricName.FAITHFULNESS:
            faithfulness_scores.append(judged.score)
        session.add(
            MetricScore(
                query_result_id=result.id,
                metric_name=metric.value,
                sample_index=sample_index,
                status=JudgmentStatus.SUCCEEDED,
                score=judged.score,
                reason=judged.reason,
                evaluator=evaluator.name,
                judge_model=run.judge_model,
                prompt_version=evaluator.prompt_version,
                judge_cached=judged.cached,
                details=judged.details,
            )
        )

    def _add_hallucination_score(
        self,
        session: AsyncSession,
        run: Run,
        evaluator: Evaluator,
        result: QueryResult,
        faithfulness_scores: list[float],
    ) -> None:
        if faithfulness_scores:
            score = max(0.0, min(1.0, 1 - statistics.fmean(faithfulness_scores)))
            session.add(
                MetricScore(
                    query_result_id=result.id,
                    metric_name=MetricName.HALLUCINATION_RATE.value,
                    sample_index=0,
                    status=JudgmentStatus.SUCCEEDED,
                    score=round(score, 6),
                    reason="Derived as 1 minus the mean faithfulness for this answer.",
                    evaluator=evaluator.name,
                    judge_model=run.judge_model,
                    prompt_version=evaluator.prompt_version,
                    judge_cached=False,
                    details={
                        "derived_from": MetricName.FAITHFULNESS.value,
                        "faithfulness_samples": len(faithfulness_scores),
                    },
                )
            )
        else:
            session.add(
                MetricScore(
                    query_result_id=result.id,
                    metric_name=MetricName.HALLUCINATION_RATE.value,
                    sample_index=0,
                    status=JudgmentStatus.FAILED,
                    score=None,
                    error_message="No successful faithfulness sample was available",
                    evaluator=evaluator.name,
                    judge_model=run.judge_model,
                    prompt_version=evaluator.prompt_version,
                    details={"derived_from": MetricName.FAITHFULNESS.value},
                )
            )

    @staticmethod
    async def _is_cancelled(session: AsyncSession, run_id: uuid.UUID) -> bool:
        run_status = await session.scalar(select(Run.status).where(Run.id == run_id))
        return run_status is RunStatus.CANCELLED

    @staticmethod
    async def _with_request_timeout(
        call: Callable[[str], Awaitable[Any]],
        question: str,
        timeout_seconds: float,
    ) -> Any:
        try:
            async with asyncio.timeout(timeout_seconds):
                return await call(question)
        except TimeoutError as exc:
            raise TimeoutError(f"Target request exceeded the {timeout_seconds:g}s timeout") from exc

    async def _mark_failed(self, run_id: uuid.UUID, message: str) -> None:
        async with self._session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None or run.status is RunStatus.CANCELLED:
                return
            run.status = RunStatus.FAILED
            run.error_message = message[:4000]
            run.finished_at = utc_now()
            await session.commit()
