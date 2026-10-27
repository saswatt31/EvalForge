from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.core.config import BACKEND_ROOT


def sample_dataset() -> str:
    lines = (
        (BACKEND_ROOT / "data" / "golden_dataset.jsonl").read_text(encoding="utf-8").splitlines()
    )
    return "\n".join(lines[:2])


async def test_run_endpoints_return_not_found(client: AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/v1/runs/{missing}/status")).status_code == 404
    assert (await client.get(f"/api/v1/runs/{missing}/results")).status_code == 404
    assert (await client.post(f"/api/v1/runs/{missing}/cancel")).status_code == 404
    compare = await client.get(
        "/api/v1/runs/compare",
        params={"baseline_id": missing, "candidate_id": missing},
    )
    assert compare.status_code == 404
    assert (await client.get(f"/api/v1/datasets/{missing}")).status_code == 404


async def test_run_creation_rejects_unknown_references(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/datasets",
        json={"name": "errors", "jsonl": sample_dataset()},
    )
    version_id = response.json()["version"]["id"]

    missing_version = await client.post(
        "/api/v1/runs",
        json={
            "dataset_version_id": str(uuid.uuid4()),
            "target_kind": "reference",
            "provider_name": "mock",
            "judge_mode": "mock",
            "judge_model": "mock-lexical-v1",
        },
    )
    assert missing_version.status_code == 422

    missing_baseline = await client.post(
        "/api/v1/runs",
        json={
            "dataset_version_id": version_id,
            "target_kind": "reference",
            "provider_name": "mock",
            "judge_mode": "mock",
            "judge_model": "mock-lexical-v1",
            "baseline_run_id": str(uuid.uuid4()),
        },
    )
    assert missing_baseline.status_code == 422

    missing_judge_key = await client.post(
        "/api/v1/runs",
        json={
            "dataset_version_id": version_id,
            "target_kind": "reference",
            "provider_name": "mock",
            "judge_mode": "llm",
            "judge_model": "judge",
            "evaluator_config": {"judge_provider": "groq"},
        },
    )
    assert missing_judge_key.status_code == 422


async def test_run_records_sanitized_target_headers_and_filters(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/datasets",
        json={"name": "headers", "jsonl": sample_dataset()},
    )
    version_id = response.json()["version"]["id"]
    created = await client.post(
        "/api/v1/runs",
        json={
            "dataset_version_id": version_id,
            "target_kind": "http",
            "provider_name": "custom",
            "target_config": {
                "url": "https://example.test/query",
                "headers": {"Authorization": "secret"},
            },
            "judge_mode": "mock",
            "judge_model": "mock-lexical-v1",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["target_config"]["header_names"] == ["Authorization"]
    assert "headers" not in body["target_config"]

    listing = await client.get(
        "/api/v1/runs",
        params={"dataset_version_id": version_id, "status": "queued"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
