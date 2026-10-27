from __future__ import annotations

import json

from httpx import AsyncClient

from app.core.config import BACKEND_ROOT


def payload() -> dict[str, object]:
    lines = (
        (BACKEND_ROOT / "data" / "golden_dataset.jsonl").read_text(encoding="utf-8").splitlines()
    )
    return {
        "name": "API dataset",
        "description": "Two synthetic records",
        "filename": "sample.jsonl",
        "jsonl": "\n".join(lines[:2]),
    }


async def test_import_list_and_fetch_dataset(client: AsyncClient) -> None:
    response = await client.post("/api/v1/datasets", json=payload())
    assert response.status_code == 201
    body = response.json()
    assert body["created_version"] is True
    assert body["dataset"]["latest_version"]["item_count"] == 2

    listing = await client.get("/api/v1/datasets")
    assert listing.status_code == 200
    assert listing.json()[0]["name"] == "API dataset"

    detail = await client.get(f"/api/v1/datasets/{body['dataset']['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["items"]) == 2
    assert detail.json()["items"][0]["reference_contexts"]


async def test_reimport_same_content_is_idempotent(client: AsyncClient) -> None:
    first = await client.post("/api/v1/datasets", json=payload())
    second = await client.post("/api/v1/datasets", json=payload())

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["created_version"] is False
    assert second.json()["version"]["id"] == first.json()["version"]["id"]


async def test_invalid_jsonl_returns_line_errors(client: AsyncClient) -> None:
    invalid = {**payload(), "jsonl": '{"question":"missing fields"}'}
    response = await client.post("/api/v1/datasets", json=invalid)

    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["line"] == 1


async def test_sample_dataset_can_be_downloaded(client: AsyncClient) -> None:
    response = await client.get("/api/v1/datasets/sample")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    first = json.loads(response.text.splitlines()[0])
    assert first["question"]


async def test_missing_dataset_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/datasets/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
