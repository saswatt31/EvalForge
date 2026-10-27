from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import BACKEND_ROOT, Settings
from app.core.enums import JudgeMode, QueryResultStatus, RunStatus, TargetKind
from app.schemas.dataset import DatasetImportRequest
from app.schemas.run import RunCreate
from app.services.datasets import import_dataset
from app.services.runs import create_run, get_run, get_run_summary
from app.storage.models import MetricScore, QueryResult, Run
from app.workers.executor import RunExecutor


def sample_jsonl(count: int) -> str:
    lines = (
        (BACKEND_ROOT / "data" / "golden_dataset.jsonl").read_text(encoding="utf-8").splitlines()
    )
    return "\n".join(lines[:count])


async def seed_run(
    session: AsyncSession,
    settings: Settings,
    *,
    top_k: int = 3,
) -> Run:
    imported = await import_dataset(
        session,
        settings,
        DatasetImportRequest(
            name=f"worker-test-{top_k}",
            jsonl=sample_jsonl(3),
            filename="sample.jsonl",
        ),
    )
    payload = RunCreate(
        name="Worker test",
        dataset_version_id=imported.version.id,
        target_kind=TargetKind.REFERENCE,
        provider_name="mock",
        model_name="mock-extractive-v1",
        pipeline_config={"top_k": top_k, "prompt_version": "reference-rag-v1"},
        judge_mode=JudgeMode.MOCK,
        judge_model="mock-lexical-v1",
    )
    return await create_run(session, settings, payload)


async def test_executor_completes_reference_run_and_caches_judgments(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    async with session_factory() as session:
        run = await seed_run(session, test_settings)
        run_id = run.id

    executor = RunExecutor(test_settings, session_factory)
    await executor.execute(run_id)

    async with session_factory() as session:
        completed = await get_run(session, run_id)
        assert completed is not None
        assert completed.status is RunStatus.SUCCEEDED
        assert completed.completed_queries == 3
        results = list(
            (await session.scalars(select(QueryResult).where(QueryResult.run_id == run_id))).all()
        )
        assert len(results) == 3
        assert all(result.status is QueryResultStatus.SUCCEEDED for result in results)
        score_count = int(
            await session.scalar(
                select(func.count())
                .select_from(MetricScore)
                .join(QueryResult, MetricScore.query_result_id == QueryResult.id)
                .where(QueryResult.run_id == run_id)
            )
            or 0
        )
        assert score_count == 12
        summary = await get_run_summary(session, completed)
        assert summary.metrics.context_recall.mean is not None
        assert summary.metrics.faithfulness.mean is not None
        assert summary.metrics.answer_relevance.mean is not None
        assert summary.metrics.cache_hits == 0
        assert summary.metrics.cache_misses == 9

        second = await seed_run(session, test_settings)
        second_id = second.id

    await executor.execute(second_id)
    async with session_factory() as session:
        second_run = await get_run(session, second_id)
        assert second_run is not None
        summary = await get_run_summary(session, second_run)
        assert summary.metrics.cache_hits == 9
        assert summary.metrics.cache_misses == 0
        assert summary.metrics.context_recall.mean is not None


async def test_executor_records_target_failures(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    async with session_factory() as session:
        imported = await import_dataset(
            session,
            test_settings,
            DatasetImportRequest(name="failed-target", jsonl=sample_jsonl(2)),
        )
        run = await create_run(
            session,
            test_settings,
            RunCreate(
                dataset_version_id=imported.version.id,
                target_kind=TargetKind.HTTP,
                provider_name="custom",
                model_name="unknown",
                target_config={
                    "url": "http://127.0.0.1:9/query",
                    "timeout_seconds": 0.2,
                },
                judge_mode=JudgeMode.MOCK,
                judge_model="mock-lexical-v1",
            ),
        )
        run_id = run.id

    await RunExecutor(test_settings, session_factory).execute(run_id)
    async with session_factory() as session:
        failed = await get_run(session, run_id)
        assert failed is not None
        assert failed.status is RunStatus.FAILED
        assert failed.failed_queries == 2
        results = list(
            (await session.scalars(select(QueryResult).where(QueryResult.run_id == run_id))).all()
        )
        assert all(result.status is QueryResultStatus.FAILED for result in results)
        assert all(result.error_message for result in results)
