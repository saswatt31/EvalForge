from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import BACKEND_ROOT, Settings
from app.core.enums import JudgeMode, RunStatus, TargetKind
from app.schemas.dataset import DatasetImportRequest
from app.schemas.run import RunCreate
from app.services.datasets import import_dataset
from app.services.runs import create_run
from app.storage.models import Run
from app.workers.manager import RunManager


async def seed_run(
    session: AsyncSession,
    settings: Settings,
    *,
    status: RunStatus = RunStatus.QUEUED,
) -> Run:
    lines = (
        (BACKEND_ROOT / "data" / "golden_dataset.jsonl").read_text(encoding="utf-8").splitlines()
    )
    imported = await import_dataset(
        session,
        settings,
        DatasetImportRequest(name=f"manager-{uuid.uuid4()}", jsonl=lines[0]),
    )
    run = await create_run(
        session,
        settings,
        RunCreate(
            dataset_version_id=imported.version.id,
            target_kind=TargetKind.REFERENCE,
            provider_name="mock",
            model_name="mock-extractive-v1",
            judge_mode=JudgeMode.MOCK,
            judge_model="mock-lexical-v1",
        ),
    )
    run.status = status
    await session.commit()
    return run


async def test_manager_recovers_interrupted_and_queued_runs(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    async with session_factory() as session:
        interrupted = await seed_run(session, test_settings, status=RunStatus.RUNNING)
        queued = await seed_run(session, test_settings, status=RunStatus.QUEUED)
        interrupted_id, queued_id = interrupted.id, queued.id

    manager = RunManager(test_settings, session_factory)
    executed: list[uuid.UUID] = []

    async def fake_execute(run_id: uuid.UUID) -> None:
        executed.append(run_id)

    manager._executor.execute = fake_execute  # type: ignore[method-assign]
    await manager.start()
    await manager.start()
    await asyncio.sleep(0.05)
    await manager.stop()
    await manager.stop()

    assert executed == [queued_id]
    async with session_factory() as session:
        failed = await session.get(Run, interrupted_id)
        assert failed is not None
        assert failed.status is RunStatus.FAILED
        assert failed.error_message
        assert failed.finished_at is not None


async def test_manager_continues_after_worker_exception(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    async with session_factory() as session:
        first = await seed_run(session, test_settings)
        second = await seed_run(session, test_settings)
        first_id, second_id = first.id, second.id

    manager = RunManager(test_settings, session_factory)
    calls: list[uuid.UUID] = []

    async def flaky_execute(run_id: uuid.UUID) -> None:
        calls.append(run_id)
        if run_id == first_id:
            raise RuntimeError("synthetic worker failure")

    manager._executor.execute = flaky_execute  # type: ignore[method-assign]
    await manager.start()
    await asyncio.sleep(0.05)
    await manager.stop()

    assert calls == [first_id, second_id]


async def test_manager_start_and_stop_without_work(
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    manager = RunManager(test_settings, session_factory)
    await manager.stop()
    await manager.start()
    await manager.stop()
