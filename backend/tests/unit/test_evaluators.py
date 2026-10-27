from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MetricName
from app.evaluators.base import EvaluationInput
from app.evaluators.cache import evaluate_with_cache
from app.evaluators.mock import MockEvaluator


@pytest.fixture
def payload() -> EvaluationInput:
    return EvaluationInput(
        question="What does TTFT measure?",
        answer="TTFT measures the time until the first generated token.",
        contexts=["Time to first token measures the delay before the first streamed token."],
        ground_truth="The delay before the first token is streamed.",
    )


async def test_mock_evaluator_is_bounded_and_deterministic(
    payload: EvaluationInput,
) -> None:
    evaluator = MockEvaluator()
    first = await evaluator.evaluate(payload, MetricName.FAITHFULNESS, sample_index=0)
    second = await evaluator.evaluate(payload, MetricName.FAITHFULNESS, sample_index=0)

    assert 0 <= first.score <= 1
    assert first.score == second.score
    assert first.details["judge_kind"] == "lexical_mock"


async def test_judge_cache_reuses_results(
    db_session: AsyncSession,
    payload: EvaluationInput,
) -> None:
    evaluator = MockEvaluator()
    first = await evaluate_with_cache(
        db_session,
        evaluator=evaluator,
        judge_model="mock-lexical-v1",
        metric=MetricName.CONTEXT_RECALL,
        sample_index=0,
        payload=payload,
    )
    second = await evaluate_with_cache(
        db_session,
        evaluator=evaluator,
        judge_model="mock-lexical-v1",
        metric=MetricName.CONTEXT_RECALL,
        sample_index=0,
        payload=payload,
    )

    assert first.cached is False
    assert second.cached is True
    assert first.score == second.score


async def test_judge_cache_separates_samples(
    db_session: AsyncSession,
    payload: EvaluationInput,
) -> None:
    evaluator = MockEvaluator()
    first = await evaluate_with_cache(
        db_session,
        evaluator=evaluator,
        judge_model="mock-lexical-v1",
        metric=MetricName.ANSWER_RELEVANCE,
        sample_index=0,
        payload=payload,
    )
    second = await evaluate_with_cache(
        db_session,
        evaluator=evaluator,
        judge_model="mock-lexical-v1",
        metric=MetricName.ANSWER_RELEVANCE,
        sample_index=1,
        payload=payload,
    )

    assert second.cached is False
    assert first.score != second.score
