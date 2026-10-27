from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.enums import MetricName
from app.evaluators.base import EvaluationInput, EvaluatorError
from app.evaluators.ragas import RagasEvaluator

PAYLOAD = EvaluationInput(
    question="How does context recall work?",
    answer="It measures whether the retrieved context covers the reference answer.",
    contexts=["Context recall measures whether retrieved evidence covers the reference."],
    ground_truth="Context recall measures coverage of the reference answer.",
)


class FakeMetric:
    def __init__(self, value: float) -> None:
        self.value = value

    async def ascore(self, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(value=self.value)


class BrokenMetric:
    async def ascore(self, **_kwargs: Any) -> SimpleNamespace:
        raise RuntimeError("judge unavailable")


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def make_evaluator(value: float = 0.8) -> RagasEvaluator:
    evaluator = object.__new__(RagasEvaluator)
    evaluator._judge_model = "judge-model"
    evaluator._context_recall = FakeMetric(value)  # type: ignore[assignment]
    evaluator._faithfulness = FakeMetric(value)  # type: ignore[assignment]
    evaluator._answer_relevancy = FakeMetric(value)  # type: ignore[assignment]
    evaluator._client = FakeClient()  # type: ignore[assignment]
    return evaluator


@pytest.mark.parametrize(
    "metric",
    [MetricName.CONTEXT_RECALL, MetricName.FAITHFULNESS, MetricName.ANSWER_RELEVANCE],
)
async def test_ragas_evaluate_maps_metrics(metric: MetricName) -> None:
    evaluator = make_evaluator(0.75)
    result = await evaluator.evaluate(PAYLOAD, metric, sample_index=2)
    assert result.metric is metric
    assert result.score == 0.75
    assert result.details["sample_index"] == 2
    assert result.details["judge_model"] == "judge-model"


async def test_ragas_evaluate_clamps_and_rejects_invalid_scores() -> None:
    evaluator = make_evaluator(1.4)
    assert (await evaluator.evaluate(PAYLOAD, MetricName.FAITHFULNESS, sample_index=0)).score == 1.0

    with pytest.raises(EvaluatorError, match="undefined"):
        await make_evaluator(math.nan).evaluate(PAYLOAD, MetricName.FAITHFULNESS, sample_index=0)

    with pytest.raises(EvaluatorError, match="Unsupported"):
        await make_evaluator().evaluate(PAYLOAD, MetricName.HALLUCINATION_RATE, sample_index=0)


async def test_ragas_metric_failure_is_wrapped(monkeypatch: Any) -> None:
    evaluator = make_evaluator()
    evaluator._faithfulness = BrokenMetric()  # type: ignore[assignment]
    with pytest.raises(EvaluatorError, match="metric failed"):
        await evaluator.evaluate(PAYLOAD, MetricName.FAITHFULNESS, sample_index=0)


async def test_ragas_close_delegates_to_client() -> None:
    evaluator = make_evaluator()
    await evaluator.aclose()
    assert evaluator._client.closed is True  # type: ignore[attr-defined]


@pytest.mark.parametrize("provider", ["ollama", "groq"])
async def test_ragas_initializes_supported_clients(
    test_settings: Settings,
    provider: str,
) -> None:
    settings = test_settings.model_copy(update={"groq_api_key": SecretStr("gsk-test-only")})
    evaluator = RagasEvaluator(
        settings,
        judge_provider=provider,
        judge_model="test-judge",
    )
    assert evaluator.name == "ragas"
    await evaluator.aclose()
