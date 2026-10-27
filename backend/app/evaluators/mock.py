from __future__ import annotations

import hashlib

from app.core.enums import MetricName
from app.evaluators.base import EvaluationInput, Evaluator, JudgeResult
from app.reference.embedding import content_tokens, lexical_overlap, supported_fraction


def _jitter(metric: MetricName, payload: EvaluationInput, sample_index: int) -> float:
    seed = "|".join(
        [
            metric.value,
            str(sample_index),
            payload.question,
            payload.answer,
            payload.ground_truth,
            "\n".join(payload.contexts),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return (int.from_bytes(digest[:4], "big") / 2**32 - 0.5) * 0.02


class MockEvaluator(Evaluator):
    name = "evalforge-mock"
    version = "1.0.0"
    prompt_version = "mock-lexical-v1"

    async def evaluate(
        self,
        payload: EvaluationInput,
        metric: MetricName,
        *,
        sample_index: int,
    ) -> JudgeResult:
        score = self._score(payload, metric)
        score = max(0.0, min(1.0, score + _jitter(metric, payload, sample_index)))
        return JudgeResult(
            metric=metric,
            score=round(score, 6),
            reason=(
                "Deterministic lexical mock judgment. This is a test fixture, "
                "not evidence of RAG quality."
            ),
            details={
                "judge_kind": "lexical_mock",
                "sample_index": sample_index,
                "metric": metric.value,
            },
        )

    def _score(self, payload: EvaluationInput, metric: MetricName) -> float:
        if metric is MetricName.CONTEXT_RECALL:
            evidence_recall = supported_fraction(payload.ground_truth, payload.contexts)
            question_relevance = lexical_overlap(payload.question, " ".join(payload.contexts))
            return min(1.0, evidence_recall * 0.9 + question_relevance * 0.1)
        if metric is MetricName.FAITHFULNESS:
            if not content_tokens(payload.answer):
                return 0.0
            return supported_fraction(payload.answer, payload.contexts)
        if metric is MetricName.ANSWER_RELEVANCE:
            question_tokens = set(content_tokens(payload.question))
            answer_tokens = set(content_tokens(payload.answer))
            if not question_tokens or not answer_tokens:
                return 0.0
            precision = len(question_tokens & answer_tokens) / len(answer_tokens)
            recall = len(question_tokens & answer_tokens) / len(question_tokens)
            if precision + recall == 0:
                return 0.0
            return 2 * precision * recall / (precision + recall)
        raise ValueError(f"Mock evaluator does not support {metric}")
