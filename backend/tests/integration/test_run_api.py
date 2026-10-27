from __future__ import annotations

import uuid
from typing import cast

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import BACKEND_ROOT, Settings
from app.services.runs import get_run
from app.workers.executor import RunExecutor


async def create_dataset(client: AsyncClient, name: str = "Run API dataset") -> dict[str, object]:
    lines = (
        (BACKEND_ROOT / "data" / "golden_dataset.jsonl").read_text(encoding="utf-8").splitlines()
    )
    response = await client.post(
        "/api/v1/datasets",
        json={"name": name, "jsonl": "\n".join(lines[:2])},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json()["version"])


async def create_run(
    client: AsyncClient,
    version_id: str,
    *,
    top_k: int = 2,
    name: str = "API run",
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/runs",
        json={
            "name": name,
            "dataset_version_id": version_id,
            "target_kind": "reference",
            "provider_name": "mock",
            "model_name": "mock-extractive-v1",
            "pipeline_config": {"top_k": top_k, "prompt_version": "reference-rag-v1"},
            "judge_mode": "mock",
            "judge_model": "mock-lexical-v1",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


async def test_run_lifecycle_results_and_compare(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    version = await create_dataset(client)
    run = await create_run(client, str(version["id"]))
    assert run["status"] == "queued"
    run_id = str(run["id"])

    await RunExecutor(test_settings, session_factory).execute(uuid.UUID(run_id))

    detail = await client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "succeeded"
    assert body["completed_queries"] == 2
    assert body["metrics"]["context_recall"]["mean"] is not None
    assert "headers" not in body["target_config"]

    results = await client.get(f"/api/v1/runs/{run_id}/results")
    assert results.status_code == 200
    page = results.json()
    assert page["total"] == 2
    assert len(page["items"][0]["metrics"]) == 4
    assert page["items"][0]["question"]

    status = await client.get(f"/api/v1/runs/{run_id}/status")
    assert status.json()["completed_queries"] == 2

    second = await create_run(client, str(version["id"]), top_k=4, name="Candidate")
    await RunExecutor(test_settings, session_factory).execute(uuid.UUID(str(second["id"])))

    compare = await client.get(
        "/api/v1/runs/compare",
        params={"baseline_id": run_id, "candidate_id": str(second["id"])},
    )
    assert compare.status_code == 200
    assert compare.json()["baseline"]["id"] == run_id
    assert len(compare.json()["rows"]) >= 8

    listing = await client.get("/api/v1/runs", params={"status": "succeeded"})
    assert listing.json()["total"] == 2

    cancel = await client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancel.status_code == 409


async def test_run_validation_and_not_found(client: AsyncClient) -> None:
    version = await create_dataset(client, name="Validation dataset")
    invalid = await client.post(
        "/api/v1/runs",
        json={
            "dataset_version_id": version["id"],
            "target_kind": "http",
            "provider_name": "custom",
            "judge_mode": "mock",
            "judge_model": "mock-lexical-v1",
        },
    )
    assert invalid.status_code == 422

    missing = await client.get("/api/v1/runs/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


async def test_meta_reports_demo_and_provider_capabilities(client: AsyncClient) -> None:
    response = await client.get("/api/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["demo_mode"] is False
    assert {provider["id"] for provider in body["providers"]} >= {"mock", "groq", "ollama"}
    assert body["sample_dataset_available"] is True
    assert body["database_ready"] is True


async def test_cancel_queued_run(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    version = await create_dataset(client, name="Cancel dataset")
    run = await create_run(client, str(version["id"]))
    response = await client.post(f"/api/v1/runs/{run['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    async with session_factory() as session:
        stored = await get_run(session, uuid.UUID(str(run["id"])))
        assert stored is not None
        assert stored.finished_at is not None
