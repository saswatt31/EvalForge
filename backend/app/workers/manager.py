from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.enums import RunStatus
from app.storage.base import utc_now
from app.storage.models import Run
from app.workers.executor import RunExecutor

logger = logging.getLogger(__name__)


class RunManager:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._executor = RunExecutor(settings, session_factory)
        self._queue: asyncio.Queue[uuid.UUID | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._current_run_id: uuid.UUID | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        await self._mark_interrupted_runs()
        self._task = asyncio.create_task(self._worker_loop(), name="evalforge-run-worker")
        async with self._session_factory() as session:
            queued = (
                await session.scalars(
                    select(Run.id).where(Run.status == RunStatus.QUEUED).order_by(Run.created_at)
                )
            ).all()
        for run_id in queued:
            await self.enqueue(run_id)

    async def enqueue(self, run_id: uuid.UUID) -> None:
        await self._queue.put(run_id)

    async def stop(self) -> None:
        if self._task is None:
            return
        await self._queue.put(None)
        try:
            await asyncio.wait_for(self._task, timeout=20)
        except TimeoutError:
            logger.warning("Worker did not stop cleanly; cancelling")
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        finally:
            self._task = None

    async def _worker_loop(self) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                if run_id is None:
                    return
                self._current_run_id = run_id
                try:
                    await self._executor.execute(run_id)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Unexpected worker failure for run %s", run_id)
            finally:
                self._current_run_id = None
                self._queue.task_done()

    async def _mark_interrupted_runs(self) -> None:
        async with self._session_factory() as session:
            interrupted = list(
                (await session.scalars(select(Run).where(Run.status == RunStatus.RUNNING))).all()
            )
            if not interrupted:
                return
            for run in interrupted:
                run.status = RunStatus.FAILED
                run.error_message = "Interrupted by an API restart before completion"
                run.finished_at = utc_now()
            await session.commit()
            logger.warning("Marked %d interrupted run(s) as failed", len(interrupted))
