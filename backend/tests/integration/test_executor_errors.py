from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import BACKEND_ROOT, Settings
from app.core.enums import JudgeMode, RunStatus, TargetKind
from app.schemas.dataset import DatasetImportRequest
from app.schemas.run import RunCreate
from app.services.datasets import import_dataset
from app.services.runs import create_run, get_run
from app.storage.base import utc_now
from app.storage.models import MetricScore, Run
from app.workers.executor import RunExecutor


def sample_jsonl(count: int = 2) -> str:
    lines = (
        (BACKEND_ROOT / "data" / "golden_dataset.jsonl").read_text(encoding="utf-8").splitlines()
    )
    return "\n".join(lines[:count])


async def make_run(
    session: AsyncSession,
    settings: Settings,
    **overrides: Any,
) -> Run:
    imported = await import_dataset(
        session,
        settings,
        DatasetImportRequest(name=f"executor-errors-{uuid.uuid4()}", jsonl=sample_jsonl()),
    )
    values: dict[str, Any] = {
        "dataset_version_id": imported.version.id,
        "target_kind": TargetKind.REFERENCE,
        "provider_name": "mock",
        "model_name": "mock-extractive-v1",
        "judge_mode": JudgeMode.MOCK,
        "judge_model": "mock-lexical-v1",
    }
    values.update(overrides)
    return await create_run(session, settings, RunCreate(**values))


async def test_executor_ignores_missing_and_finished_runs(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    executor = RunExecutor(test_settings, session_factory)
    await executor.execute(uuid.uuid4())

    async with session_factory() as session:
        completed = await make_run(session, test_settings)
        completed.status = RunStatus.SUCCEEDED
        completed.finished_at = utc_now()
        await session.commit()
        completed_id = completed.id

    await executor.execute(completed_id)

    async with session_factory() as session:
        stored = await session.get(Run, completed_id)
        assert stored is not None
        assert stored.status is RunStatus.SUCCEEDED


async def test_executor_marks_initialization_failure(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    async with session_factory() as session:
        run = await make_run(session, test_settings, provider_name="groq")
        run_id = run.id

    await RunExecutor(test_settings, session_factory).execute(run_id)

    async with session_factory() as session:
        failed = await get_run(session, run_id)
        assert failed is not None
        assert failed.status is RunStatus.FAILED
        assert failed.error_message
        assert "initialization failed" in failed.error_message


async def test_executor_records_failed_judgments(
    monkeypatch: Any,
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    async def failing_judge(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("synthetic judge outage")

    monkeypatch.setattr("app.workers.executor.evaluate_with_cache", failing_judge)
    async with session_factory() as session:
        run = await make_run(session, test_settings)
        run_id = run.id

    await RunExecutor(test_settings, session_factory).execute(run_id)

    async with session_factory() as session:
        completed = await get_run(session, run_id)
        assert completed is not None
        assert completed.status is RunStatus.SUCCEEDED
        failed_scores = int(
            await session.scalar(
                select(func.count()).select_from(MetricScore).where(MetricScore.status == "failed")
            )
            or 0
        )
        assert failed_scores == 8


async def test_executor_marks_cancelled_and_incomplete_runs(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    executor = RunExecutor(test_settings, session_factory)
    async with session_factory() as session:
        run = await make_run(session, test_settings)
        run.status = RunStatus.CANCELLED
        await session.commit()
        run_id = run.id

    await executor._run_items(run_id, [], None, None)  # type: ignore[arg-type]

    async with session_factory() as session:
        stored = await get_run(session, run_id)
        assert stored is not None
        stored.status = RunStatus.QUEUED
        stored.total_queries = 99
        await session.commit()

    await executor.execute(run_id)
    async with session_factory() as session:
        completed = await get_run(session, run_id)
        assert completed is not None
        assert completed.status is RunStatus.CANCELLED


async def test_executor_marks_failed_run_cancelled_and_timeout(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    async with session_factory() as session:
        run = await make_run(session, test_settings)
        run.status = RunStatus.CANCELLED
        await session.commit()
        run_id = run.id

    executor = RunExecutor(test_settings, session_factory)
    await executor._mark_failed(run_id, "should not override")

    async def slow(_question: str) -> None:
        await asyncio.sleep(1)

    with pytest.raises(TimeoutError, match="timeout"):
        await executor._with_request_timeout(slow, "question", 0.01)
