from __future__ import annotations

import math
from typing import Any

from app.core.config import Settings
from app.core.enums import MetricName
from app.evaluators.base import EvaluationInput, Evaluator, EvaluatorError, JudgeResult
from app.reference.embedding import HashEmbedding

RAGAS_PROMPT_VERSION = "ragas-0.4.3-collections-v1"


class RagasEvaluator(Evaluator):
    name = "ragas"
    version = "0.4.3"
    prompt_version = RAGAS_PROMPT_VERSION

    def __init__(self, settings: Settings, *, judge_provider: str, judge_model: str) -> None:
        try:
            from openai import AsyncOpenAI
            from ragas.llms import llm_factory
            from ragas.metrics.collections import (
                AnswerRelevancy,
                ContextRecall,
                Faithfulness,
            )
        except ImportError as exc:
            raise EvaluatorError(
                "Ragas judge dependencies are unavailable. Install the backend package "
                "with its evaluation dependencies."
            ) from exc

        provider = judge_provider.lower()
        if provider == "groq":
            if settings.groq_api_key is None:
                raise EvaluatorError("Groq judge requires EVALFORGE_GROQ_API_KEY")
            client = AsyncOpenAI(
                api_key=settings.groq_api_key.get_secret_value(),
                base_url=settings.groq_base_url,
                timeout=settings.judge_timeout_seconds,
            )
        elif provider == "ollama":
            client = AsyncOpenAI(
                api_key="ollama",
                base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
                timeout=settings.judge_timeout_seconds,
            )
        else:
            raise EvaluatorError(f"Unsupported judge provider: {judge_provider}")

        self._client = client
        self._judge_model = judge_model
        try:
            llm = llm_factory(
                judge_model,
                provider="openai",
                client=client,
                max_tokens=2048,
                temperature=0.0,
            )
            embeddings = HashEmbedding()
            self._faithfulness = Faithfulness(llm=llm)
            self._context_recall = ContextRecall(llm=llm)
            self._answer_relevancy = AnswerRelevancy(
                llm=llm,
                embeddings=embeddings,
                strictness=3,
            )
        except Exception as exc:
            raise EvaluatorError(f"Could not initialize Ragas metrics: {exc}") from exc

    async def evaluate(
        self,
        payload: EvaluationInput,
        metric: MetricName,
        *,
        sample_index: int,
    ) -> JudgeResult:
        try:
            if metric is MetricName.CONTEXT_RECALL:
                result = await self._context_recall.ascore(
                    user_input=payload.question,
                    retrieved_contexts=payload.contexts,
                    reference=payload.ground_truth,
                )
            elif metric is MetricName.FAITHFULNESS:
                result = await self._faithfulness.ascore(
                    user_input=payload.question,
                    response=payload.answer,
                    retrieved_contexts=payload.contexts,
                )
            elif metric is MetricName.ANSWER_RELEVANCE:
                result = await self._answer_relevancy.ascore(
                    user_input=payload.question,
                    response=payload.answer,
                )
            else:
                raise EvaluatorError(f"Unsupported Ragas metric: {metric}")
        except Exception as exc:
            raise EvaluatorError(f"Ragas metric failed: {exc}") from exc

        score = float(result.value)
        if math.isnan(score) or math.isinf(score):
            raise EvaluatorError("Ragas returned an undefined score")
        score = max(0.0, min(1.0, score))
        return JudgeResult(
            metric=metric,
            score=round(score, 6),
            reason="Score computed by the Ragas metric pipeline.",
            details={
                "judge_kind": "ragas",
                "ragas_version": self.version,
                "prompt_version": self.prompt_version,
                "sample_index": sample_index,
                "judge_model": self._judge_model,
            },
        )

    async def aclose(self) -> None:
        await self._client.close()


def build_ragas_evaluator(
    settings: Settings,
    evaluator_config: dict[str, Any],
) -> RagasEvaluator:
    judge_provider = str(evaluator_config.get("judge_provider", settings.judge_provider))
    judge_model = str(evaluator_config.get("judge_model", settings.judge_model))
    return RagasEvaluator(
        settings,
        judge_provider=judge_provider,
        judge_model=judge_model,
    )
