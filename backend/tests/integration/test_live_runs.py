from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.api.routes.runs as runs_route
from app.core.config import BACKEND_ROOT, Settings
from app.services.live_runs import hash_client_ip
from app.storage.models import QueryResult, Run
from app.workers.executor import RunExecutor


def sample_jsonl(count: int) -> str:
    lines = (
        (BACKEND_ROOT / "data" / "golden_dataset.jsonl").read_text(encoding="utf-8").splitlines()
    )
    return "\n".join(lines[:count])


async def create_dataset(client: AsyncClient, count: int = 12) -> str:
    response = await client.post(
        "/api/v1/datasets",
        json={"name": f"live-run-{count}", "jsonl": sample_jsonl(count)},
    )
    assert response.status_code == 201
    return str(response.json()["version"]["id"])


def run_payload(version_id: str) -> dict[str, Any]:
    return {
        "name": "Free-tier mini-suite",
        "dataset_version_id": version_id,
        "target_kind": "reference",
        "provider_name": "mock",
        "model_name": "mock-extractive-v1",
        "pipeline_config": {"top_k": 2, "prompt_version": "reference-rag-v1"},
        "judge_mode": "mock",
        "judge_model": "mock-lexical-v1",
    }


def protected_settings(test_settings: Settings) -> Settings:
    return test_settings.model_copy(
        update={
            "live_run_protection": True,
            "live_run_max_queries": 10,
            "live_run_daily_cap": 2,
            "live_run_per_ip_limit": 1,
            "live_run_rate_window_seconds": 3_600,
        }
    )


async def test_live_run_cap_and_rate_limit(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = protected_settings(test_settings)
    monkeypatch.setattr(runs_route, "get_settings", lambda: settings)
    version_id = await create_dataset(client)

    first = await client.post(
        "/api/v1/runs",
        json=run_payload(version_id),
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert first.status_code == 201, first.text
    run = first.json()
    assert run["total_queries"] == 10

    async with session_factory() as session:
        stored = await session.get(Run, uuid.UUID(run["id"]))
        assert stored is not None
        assert stored.client_ip_hash == hash_client_ip(settings, "203.0.113.10")

    repeated = await client.post(
        "/api/v1/runs",
        json=run_payload(version_id),
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert repeated.status_code == 429
    detail = repeated.json()["detail"]
    assert detail["code"] == "live_runs_paused"
    assert detail["reason"] == "per_ip"
    assert detail["retry_after_seconds"] > 0
    assert repeated.headers["retry-after"] == str(detail["retry_after_seconds"])

    second_ip = await client.post(
        "/api/v1/runs",
        json=run_payload(version_id),
        headers={"X-Forwarded-For": "203.0.113.11"},
    )
    assert second_ip.status_code == 201, second_ip.text

    third_ip = await client.post(
        "/api/v1/runs",
        json=run_payload(version_id),
        headers={"X-Forwarded-For": "203.0.113.12"},
    )
    assert third_ip.status_code == 429
    daily = third_ip.json()["detail"]
    assert daily["code"] == "live_runs_paused"
    assert daily["reason"] == "daily"
    assert daily["limit"] == 2

    async with session_factory() as session:
        runs = list((await session.scalars(select(Run).order_by(Run.created_at))).all())
        assert len(runs) == 2

    await RunExecutor(settings, session_factory).execute(uuid.UUID(run["id"]))
    async with session_factory() as session:
        completed = await session.get(Run, uuid.UUID(run["id"]))
        assert completed is not None
        assert completed.completed_queries == 10
        result_count = int(
            await session.scalar(
                select(func.count())
                .select_from(QueryResult)
                .where(QueryResult.run_id == completed.id)
            )
            or 0
        )
        assert result_count == 10


async def test_live_run_protection_is_off_by_default(
    client: AsyncClient,
    test_settings: Settings,
) -> None:
    version_id = await create_dataset(client)
    response = await client.post(
        "/api/v1/runs",
        json=run_payload(version_id),
        headers={"X-Forwarded-For": "203.0.113.20"},
    )
    assert response.status_code == 201
    assert response.json()["total_queries"] == 12
