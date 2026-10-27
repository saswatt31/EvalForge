from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.cli import (
    ApiClient,
    CLIError,
    ThresholdError,
    _compare_command,
    _datasets_command,
    _run_command,
    build_parser,
)

RUN_ID = "11111111-1111-1111-1111-111111111111"
VERSION_ID = "22222222-2222-2222-2222-222222222222"


def run_summary(*, status: str = "succeeded", faithfulness: float = 0.8) -> dict[str, Any]:
    metric = {"mean": faithfulness, "judged_queries": 2, "total_samples": 2, "failed_samples": 0}
    return {
        "id": RUN_ID,
        "name": "CLI run",
        "status": status,
        "completed_queries": 2,
        "failed_queries": 0,
        "total_queries": 2,
        "config_hash": "a" * 64,
        "judge_model": "mock-lexical-v1",
        "source": "cli",
        "metrics": {
            "context_recall": metric,
            "faithfulness": metric,
            "answer_relevance": metric,
            "hallucination_rate": metric,
            "latency": {
                "p50_ms": 12.0,
                "p95_ms": 20.0,
                "mean_ms": 13.0,
                "ttft_p50_ms": 5.0,
                "ttft_p95_ms": 8.0,
                "measured_ttft_count": 2,
                "target_reported_ttft_count": 0,
                "demo_ttft_count": 0,
                "mean_tokens_per_second": 30.0,
            },
            "success_rate": 1.0,
            "cache_hits": 0,
            "cache_misses": 8,
        },
    }


def handler_factory(statuses: list[str]) -> httpx.MockTransport:
    statuses = list(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/datasets") and request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "dataset": {"id": VERSION_ID, "latest_version": {"id": VERSION_ID}},
                    "version": {"id": VERSION_ID},
                    "created_version": True,
                },
            )
        if path.endswith("/datasets") and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": VERSION_ID,
                        "name": "Dataset",
                        "latest_version": {
                            "id": VERSION_ID,
                            "version_number": 1,
                            "item_count": 2,
                        },
                    }
                ],
            )
        if path.endswith("/runs") and request.method == "POST":
            return httpx.Response(201, json=run_summary(status="queued"))
        if path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "id": RUN_ID,
                    "status": statuses.pop(0) if len(statuses) > 1 else statuses[0],
                    "completed_queries": 1,
                    "failed_queries": 0,
                    "total_queries": 2,
                },
            )
        if path.endswith("/compare"):
            return httpx.Response(
                200,
                json={
                    "baseline": run_summary(),
                    "candidate": run_summary(faithfulness=0.9),
                    "rows": [
                        {
                            "metric": "faithfulness",
                            "baseline": 0.8,
                            "candidate": 0.9,
                            "delta": 0.1,
                            "relative_delta": 0.125,
                        }
                    ],
                },
            )
        return httpx.Response(200, json=run_summary())

    return httpx.MockTransport(handler)


def args_for(command: list[str]) -> Any:
    return build_parser().parse_args(command)


async def test_cli_run_waits_and_prints_json(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"question":"q"}\n', encoding="utf-8")
    client = ApiClient("http://test/api/v1", transport=handler_factory(["running", "succeeded"]))
    stdout, stderr = io.StringIO(), io.StringIO()
    args = args_for(
        [
            "run",
            "--dataset",
            str(dataset),
            "--json",
            "--poll-interval",
            "0",
        ]
    )

    code = _run_command(args, client, stdout, stderr)

    assert code == 0
    assert json.loads(stdout.getvalue())["status"] == "succeeded"
    client.close()


async def test_cli_run_applies_thresholds_and_writes_markdown(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("{}", encoding="utf-8")
    markdown = tmp_path / "comment.md"
    client = ApiClient("http://test/api/v1", transport=handler_factory(["succeeded"]))
    args = args_for(
        [
            "run",
            "--dataset",
            str(dataset),
            "--min-faithfulness",
            "0.95",
            "--max-p95-latency-ms",
            "10",
            "--markdown",
            str(markdown),
        ]
    )

    with pytest.raises(ThresholdError, match="faithfulness"):
        _run_command(args, client, io.StringIO(), io.StringIO())
    assert "EvalForge evaluation" in markdown.read_text(encoding="utf-8")
    client.close()


async def test_cli_compare_and_datasets_output() -> None:
    client = ApiClient("http://test/api/v1", transport=handler_factory(["succeeded"]))
    stdout = io.StringIO()
    code = _compare_command(
        args_for(["compare", "--baseline", "a", "--candidate", "b"]),
        client,
        stdout,
    )
    assert code == 0
    assert "faithfulness" in stdout.getvalue()

    stdout = io.StringIO()
    code = _datasets_command(args_for(["datasets"]), client, stdout)
    assert code == 0
    assert "v1" in stdout.getvalue()
    client.close()


def test_cli_reports_api_errors_and_requires_http_url(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized"})

    client = ApiClient("http://test/api/v1", transport=httpx.MockTransport(handler))
    args = args_for(["datasets"])
    with pytest.raises(CLIError, match="HTTP 401"):
        client.list_datasets()

    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("{}", encoding="utf-8")
    args = args_for(["run", "--dataset", str(dataset), "--target", "http"])
    with pytest.raises(CLIError, match="--url"):
        _run_command(args, client, io.StringIO(), io.StringIO())
    client.close()
