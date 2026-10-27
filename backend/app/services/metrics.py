from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Iterable

from app.core.enums import JudgmentStatus, MetricName, QueryResultStatus, TTFTSource
from app.schemas.run import LatencyAggregate, MetricAggregate, RunMetrics
from app.storage.models import MetricScore, QueryResult

JUDGE_METRICS = (
    MetricName.CONTEXT_RECALL,
    MetricName.FAITHFULNESS,
    MetricName.ANSWER_RELEVANCE,
)
JUDGE_METRIC_VALUES = {metric.value for metric in JUDGE_METRICS}


def percentile(values: Iterable[float], percentile_value: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile_value
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _metric_aggregate(
    scores: list[MetricScore],
    metric: MetricName,
) -> MetricAggregate:
    matching = [score for score in scores if score.metric_name == metric.value]
    successful = [score for score in matching if score.status is JudgmentStatus.SUCCEEDED]
    by_result: dict[object, list[float]] = defaultdict(list)
    for score in successful:
        if score.score is not None:
            by_result[score.query_result_id].append(score.score)
    per_query = [sum(values) / len(values) for values in by_result.values() if values]
    return MetricAggregate(
        mean=round(sum(per_query) / len(per_query), 6) if per_query else None,
        judged_queries=len(per_query),
        total_samples=len(matching),
        failed_samples=len(matching) - len(successful),
    )


def aggregate_run_metrics(
    *,
    total_queries: int,
    query_results: list[QueryResult],
    scores: list[MetricScore],
) -> RunMetrics:
    succeeded_results = [
        result for result in query_results if result.status is QueryResultStatus.SUCCEEDED
    ]
    latencies = [result.latency_ms for result in succeeded_results if result.latency_ms is not None]
    ttfts = [result.ttft_ms for result in succeeded_results if result.ttft_ms is not None]
    throughput = [
        result.tokens_per_second
        for result in succeeded_results
        if result.tokens_per_second is not None
    ]

    hallucinations: list[float] = []
    for result in succeeded_results:
        faithfulness = [
            score.score
            for score in scores
            if score.query_result_id == result.id
            and score.metric_name == MetricName.FAITHFULNESS.value
            and score.status is JudgmentStatus.SUCCEEDED
            and score.score is not None
        ]
        if faithfulness:
            hallucinations.append(1 - sum(faithfulness) / len(faithfulness))
    hallucination_aggregate = MetricAggregate(
        mean=round(sum(hallucinations) / len(hallucinations), 6) if hallucinations else None,
        judged_queries=len(hallucinations),
        total_samples=len(hallucinations),
        failed_samples=0,
    )

    latency_p50 = percentile(latencies, 0.5)
    latency_p95 = percentile(latencies, 0.95)
    ttft_p50 = percentile(ttfts, 0.5)
    ttft_p95 = percentile(ttfts, 0.95)
    latency = LatencyAggregate(
        p50_ms=round(latency_p50, 3) if latency_p50 is not None else None,
        p95_ms=round(latency_p95, 3) if latency_p95 is not None else None,
        mean_ms=round(statistics.fmean(latencies), 3) if latencies else None,
        ttft_p50_ms=round(ttft_p50, 3) if ttft_p50 is not None else None,
        ttft_p95_ms=round(ttft_p95, 3) if ttft_p95 is not None else None,
        measured_ttft_count=sum(
            result.ttft_source is TTFTSource.MEASURED and result.ttft_ms is not None
            for result in succeeded_results
        ),
        target_reported_ttft_count=sum(
            result.ttft_source is TTFTSource.TARGET_REPORTED and result.ttft_ms is not None
            for result in succeeded_results
        ),
        demo_ttft_count=sum(
            result.ttft_source is TTFTSource.DEMO and result.ttft_ms is not None
            for result in succeeded_results
        ),
        mean_tokens_per_second=(round(statistics.fmean(throughput), 3) if throughput else None),
    )
    judged_scores = [score for score in scores if score.metric_name in JUDGE_METRIC_VALUES]
    return RunMetrics(
        context_recall=_metric_aggregate(scores, MetricName.CONTEXT_RECALL),
        faithfulness=_metric_aggregate(scores, MetricName.FAITHFULNESS),
        answer_relevance=_metric_aggregate(scores, MetricName.ANSWER_RELEVANCE),
        hallucination_rate=hallucination_aggregate,
        latency=latency,
        success_rate=(round(len(succeeded_results) / total_queries, 6) if total_queries else None),
        cache_hits=sum(score.judge_cached for score in judged_scores),
        cache_misses=sum(not score.judge_cached for score in judged_scores),
    )
