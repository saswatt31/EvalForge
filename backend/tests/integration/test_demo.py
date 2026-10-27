from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import RunSource, RunStatus, TTFTSource
from app.services.demo import seed_demo_data
from app.storage.models import QueryResult, Run


async def test_demo_seed_creates_two_labelled_runs(
    db_session: AsyncSession,
    test_settings: Settings,
) -> None:
    test_settings.demo_mode = True
    await seed_demo_data(db_session, test_settings)
    await seed_demo_data(db_session, test_settings)

    runs = list((await db_session.scalars(select(Run).order_by(Run.created_at))).all())
    assert len(runs) == 2
    assert all(run.source is RunSource.DEMO for run in runs)
    assert all(run.status is RunStatus.SUCCEEDED for run in runs)
    assert runs[0].completed_queries == 112

    result_count = int(await db_session.scalar(select(func.count()).select_from(QueryResult)) or 0)
    assert result_count == 224
    result = await db_session.scalar(select(QueryResult).limit(1))
    assert result is not None
    assert result.ttft_source is TTFTSource.DEMO
    assert result.latency_ms is not None


async def test_demo_seed_skips_when_runs_exist(
    db_session: AsyncSession,
    test_settings: Settings,
) -> None:
    await seed_demo_data(db_session, test_settings)
    await seed_demo_data(db_session, test_settings)
    count = int(await db_session.scalar(select(func.count()).select_from(Run)) or 0)
    assert count == 2
