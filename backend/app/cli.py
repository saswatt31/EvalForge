from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

import httpx

TERMINAL_STATUSES = {"succeeded", "partial", "failed", "cancelled"}


class CLIError(RuntimeError):
    pass


class ThresholdError(RuntimeError):
    pass


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"X-API-Key": token} if token else {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise CLIError(f"Could not reach the EvalForge API: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            if isinstance(detail, dict):
                detail = detail.get("message", json.dumps(detail))
            raise CLIError(f"API returned HTTP {response.status_code}: {detail}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise CLIError("API returned a non-JSON response") from exc

    def import_dataset(self, name: str, path: Path) -> dict[str, Any]:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CLIError(f"Could not read dataset: {exc}") from exc
        return _expect_dict(
            self._request(
                "POST",
                "/datasets",
                json={
                    "name": name,
                    "description": f"Imported by evalforge CLI from {path.name}",
                    "filename": path.name,
                    "jsonl": content,
                },
            )
        )

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _expect_dict(self._request("POST", "/runs", json=payload))

    def get_run(self, run_id: str) -> dict[str, Any]:
        return _expect_dict(self._request("GET", f"/runs/{run_id}"))

    def get_run_status(self, run_id: str) -> dict[str, Any]:
        return _expect_dict(self._request("GET", f"/runs/{run_id}/status"))

    def compare(self, baseline_id: str, candidate_id: str) -> dict[str, Any]:
        return _expect_dict(
            self._request(
                "GET",
                "/runs/compare",
                params={"baseline_id": baseline_id, "candidate_id": candidate_id},
            )
        )

    def list_datasets(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/datasets")
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise CLIError("API returned an unexpected dataset list")
        return data


def _expect_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CLIError("API returned an unexpected response shape")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalforge",
        description="Run and compare RAG quality and latency benchmarks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Evaluate a golden dataset")
    run_parser.add_argument("--dataset", type=Path, required=True)
    run_parser.add_argument("--name")
    run_parser.add_argument("--target", choices=["reference", "http"], default="reference")
    run_parser.add_argument("--url", help="RAG endpoint for an HTTP target")
    run_parser.add_argument("--streaming", action="store_true")
    run_parser.add_argument("--provider", default="mock")
    run_parser.add_argument("--model")
    run_parser.add_argument("--top-k", type=int, default=5)
    run_parser.add_argument("--judge", choices=["mock", "llm"], default="mock")
    run_parser.add_argument("--judge-provider", choices=["groq", "ollama"], default="groq")
    run_parser.add_argument("--judge-model")
    run_parser.add_argument("--repeats", type=int, default=1)
    run_parser.add_argument("--warmup", type=int, default=0)
    run_parser.add_argument("--baseline")
    run_parser.add_argument("--source", choices=["dashboard", "cli", "ci"], default="cli")
    run_parser.add_argument("--git-sha")
    run_parser.add_argument("--git-branch")
    run_parser.add_argument("--pull-request", type=int)
    run_parser.add_argument("--min-context-recall", type=float)
    run_parser.add_argument("--min-faithfulness", type=float)
    run_parser.add_argument("--min-answer-relevance", type=float)
    run_parser.add_argument("--max-hallucination-rate", type=float)
    run_parser.add_argument("--max-p95-latency-ms", type=float)
    run_parser.add_argument("--timeout", type=float, default=1800)
    run_parser.add_argument("--poll-interval", type=float, default=1.0)
    run_parser.add_argument("--markdown", type=Path)
    _add_common(run_parser)

    compare_parser = subparsers.add_parser("compare", help="Compare two completed runs")
    compare_parser.add_argument("--baseline", required=True)
    compare_parser.add_argument("--candidate", required=True)
    _add_common(compare_parser)

    datasets_parser = subparsers.add_parser("datasets", help="List datasets")
    _add_common(datasets_parser)
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-url",
        default=os.environ.get("EVALFORGE_API_URL", "http://localhost:8000/api/v1"),
    )
    parser.add_argument("--token", default=os.environ.get("EVALFORGE_WRITE_API_TOKEN"))
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")


def _resolve_model(args: argparse.Namespace) -> str | None:
    if args.model:
        return str(args.model)
    if args.provider == "groq":
        return "llama-3.3-70b-versatile"
    if args.provider == "ollama":
        return "llama3.1"
    if args.provider == "mock":
        return "mock-extractive-v1"
    return None


def _run_payload(args: argparse.Namespace, version_id: str) -> dict[str, Any]:
    if args.target == "http" and not args.url:
        raise CLIError("--url is required for an HTTP target")
    if args.judge == "llm" and not args.judge_model:
        if args.judge_provider == "groq":
            args.judge_model = "llama-3.3-70b-versatile"
        else:
            args.judge_model = "llama3.1"
    payload: dict[str, Any] = {
        "name": args.name,
        "dataset_version_id": version_id,
        "target_kind": args.target,
        "provider_name": args.provider,
        "model_name": _resolve_model(args),
        "target_config": {"url": args.url, "streaming": args.streaming}
        if args.target == "http"
        else {},
        "pipeline_config": {"top_k": args.top_k, "prompt_version": "reference-rag-v1"},
        "judge_mode": args.judge,
        "judge_model": args.judge_model or "mock-lexical-v1",
        "judge_repeats": args.repeats,
        "evaluator_config": {"judge_provider": args.judge_provider},
        "warmup_count": args.warmup,
        "baseline_run_id": args.baseline,
        "source": args.source,
        "git_sha": args.git_sha,
        "git_branch": args.git_branch,
        "pull_request_number": args.pull_request,
    }
    return {key: value for key, value in payload.items() if value is not None}


def _wait(
    client: ApiClient,
    run_id: str,
    *,
    timeout: float,
    poll_interval: float,
    error_stream: TextIO,
) -> dict[str, Any]:
    started = time.monotonic()
    while True:
        state = client.get_run_status(run_id)
        if state["status"] in TERMINAL_STATUSES:
            return client.get_run(run_id)
        if time.monotonic() - started > timeout:
            raise CLIError(f"Run did not finish within {timeout:g}s")
        print(
            f"run {run_id[:8]} {state['status']} "
            f"{state['completed_queries']}/{state['total_queries']} "
            f"({state['failed_queries']} failed)",
            file=error_stream,
        )
        time.sleep(poll_interval)


def _metric_value(run: dict[str, Any], key: str) -> float | None:
    metrics = run["metrics"]
    if key in {"context_recall", "faithfulness", "answer_relevance", "hallucination_rate"}:
        value = metrics[key]["mean"]
    elif key == "p95_latency":
        value = metrics["latency"]["p95_ms"]
    else:
        value = None
    return float(value) if value is not None else None


def _check_thresholds(run: dict[str, Any], args: argparse.Namespace) -> None:
    checks = [
        ("context_recall", args.min_context_recall, "min"),
        ("faithfulness", args.min_faithfulness, "min"),
        ("answer_relevance", args.min_answer_relevance, "min"),
        ("hallucination_rate", args.max_hallucination_rate, "max"),
        ("p95_latency", args.max_p95_latency_ms, "max"),
    ]
    failures: list[str] = []
    for key, threshold, direction in checks:
        if threshold is None:
            continue
        value = _metric_value(run, key)
        if value is None:
            failures.append(f"{key} unavailable (threshold {threshold:g})")
        elif direction == "min" and value < threshold:
            failures.append(f"{key}={value:.4f} is below {threshold:g}")
        elif direction == "max" and value > threshold:
            failures.append(f"{key}={value:.4f} is above {threshold:g}")
    if failures:
        raise ThresholdError("; ".join(failures))


def _markdown(run: dict[str, Any]) -> str:
    metrics = run["metrics"]
    latency = metrics["latency"]
    quality = [
        ("Context recall", "context_recall"),
        ("Faithfulness", "faithfulness"),
        ("Answer relevance", "answer_relevance"),
        ("Hallucination rate", "hallucination_rate"),
    ]
    lines = [
        "## EvalForge evaluation",
        "",
        f"**Run:** `{run['name']}`  ",
        (
            f"**Status:** `{run['status']}` · "
            f"{run['completed_queries']}/{run['total_queries']} succeeded · "
            f"{run['failed_queries']} failed"
        ),
        f"**Run ID:** `{run['id']}`  ",
        (
            f"**Config:** `{run['config_hash'][:12]}` · "
            f"Judge `{run['judge_model']}` ({run.get('judge_mode', 'unknown')})"
        ),
        "",
        "| Metric | Value | Judged | Failed samples |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key in quality:
        metric = metrics[key]
        value = metric["mean"]
        rendered = "n/a" if value is None else f"{float(value) * 100:.1f}%"
        lines.append(
            f"| {label} | {rendered} | {metric['judged_queries']} | {metric['failed_samples']} |"
        )
    lines.extend(
        [
            "",
            (
                f"**Latency:** p50 {_fmt(latency['p50_ms'], ' ms')} · "
                f"p95 {_fmt(latency['p95_ms'], ' ms')} · "
                f"TTFT p50 {_fmt(latency['ttft_p50_ms'], ' ms')}"
            ),
            (
                f"**Success rate:** {_fmt(metrics['success_rate'])} · "
                f"**Judge cache:** {metrics['cache_hits']} hits / "
                f"{metrics['cache_misses']} misses"
            ),
        ]
    )
    return "\n".join(lines)


def _print_run(run: dict[str, Any], stream: TextIO) -> None:
    metrics = run["metrics"]
    latency = metrics["latency"]
    print(f"Run {run['name']} [{run['status']}]", file=stream)
    print(f"  context recall     {_fmt(metrics['context_recall']['mean'])}", file=stream)
    print(f"  faithfulness       {_fmt(metrics['faithfulness']['mean'])}", file=stream)
    print(f"  answer relevance   {_fmt(metrics['answer_relevance']['mean'])}", file=stream)
    print(f"  hallucination rate {_fmt(metrics['hallucination_rate']['mean'])}", file=stream)
    print(
        f"  latency p50/p95    {_fmt(latency['p50_ms'], ' ms')} / {_fmt(latency['p95_ms'], ' ms')}",
        file=stream,
    )
    print(
        f"  TTFT p50/p95       {_fmt(latency['ttft_p50_ms'], ' ms')} / "
        f"{_fmt(latency['ttft_p95_ms'], ' ms')}",
        file=stream,
    )
    print(f"  cache hits/misses  {metrics['cache_hits']} / {metrics['cache_misses']}", file=stream)


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}{suffix}"


def _run_command(
    args: argparse.Namespace,
    client: ApiClient,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if args.target == "http" and not args.url:
        raise CLIError("--url is required for an HTTP target")
    dataset_path: Path = args.dataset
    name = args.name or dataset_path.stem
    imported = client.import_dataset(name, dataset_path)
    version_id = imported["version"]["id"]
    run = client.create_run(_run_payload(args, version_id))
    print(f"queued run {run['id']}", file=stderr)
    completed = _wait(
        client,
        run["id"],
        timeout=args.timeout,
        poll_interval=args.poll_interval,
        error_stream=stderr,
    )
    if args.json:
        print(json.dumps(completed, indent=2), file=stdout)
    else:
        _print_run(completed, stdout)
    if args.markdown:
        args.markdown.write_text(_markdown(completed), encoding="utf-8")
    if completed["status"] not in {"succeeded", "partial"}:
        raise CLIError(f"Run finished with status {completed['status']}")
    if completed["status"] == "partial":
        raise ThresholdError(
            f"{completed['failed_queries']} of {completed['total_queries']} queries failed"
        )
    _check_thresholds(completed, args)
    return 0


def _compare_command(
    args: argparse.Namespace,
    client: ApiClient,
    stdout: TextIO,
) -> int:
    result = client.compare(args.baseline, args.candidate)
    if args.json:
        print(json.dumps(result, indent=2), file=stdout)
        return 0
    print(
        f"Baseline:  {result['baseline']['name']}\nCandidate: {result['candidate']['name']}\n",
        file=stdout,
    )
    print(
        f"{'metric':<24} {'baseline':>10} {'candidate':>10} {'delta':>10}",
        file=stdout,
    )
    for row in result["rows"]:
        print(
            f"{row['metric']:<24} {_fmt(row['baseline']):>10} "
            f"{_fmt(row['candidate']):>10} {_fmt(row['delta']):>10}",
            file=stdout,
        )
    return 0


def _datasets_command(args: argparse.Namespace, client: ApiClient, stdout: TextIO) -> int:
    datasets = client.list_datasets()
    if args.json:
        print(json.dumps(datasets, indent=2), file=stdout)
        return 0
    if not datasets:
        print("No datasets yet.", file=stdout)
        return 0
    for dataset in datasets:
        version = dataset["latest_version"]
        print(
            f"{dataset['name']}  v{version['version_number']}  "
            f"{version['item_count']} queries  {dataset['id']}",
            file=stdout,
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = ApiClient(args.api_url, token=args.token)
    try:
        if args.command == "run":
            return _run_command(args, client, sys.stdout, sys.stderr)
        if args.command == "compare":
            return _compare_command(args, client, sys.stdout)
        return _datasets_command(args, client, sys.stdout)
    except ThresholdError as exc:
        print(f"Threshold failed: {exc}", file=sys.stderr)
        return 1
    except CLIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
