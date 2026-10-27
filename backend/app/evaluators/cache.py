from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MetricName
from app.evaluators.base import EvaluationInput, Evaluator
from app.storage.base import utc_now
from app.storage.models import JudgeCacheEntry


@dataclass(frozen=True, slots=True)
class CachedJudgment:
    score: float
    reason: str | None
    details: dict[str, Any]
    cached: bool


def build_cache_key(
    *,
    evaluator: Evaluator,
    judge_model: str,
    metric: MetricName,
    sample_index: int,
    payload: EvaluationInput,
) -> str:
    canonical = {
        "evaluator": evaluator.name,
        "evaluator_version": evaluator.version,
        "prompt_version": evaluator.prompt_version,
        "judge_model": judge_model,
        "metric": metric.value,
        "sample_index": sample_index,
        "question": payload.question,
        "answer": payload.answer,
        "contexts": payload.contexts,
        "ground_truth": payload.ground_truth,
    }
    serialized = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def evaluate_with_cache(
    session: AsyncSession,
    *,
    evaluator: Evaluator,
    judge_model: str,
    metric: MetricName,
    sample_index: int,
    payload: EvaluationInput,
) -> CachedJudgment:
    cache_key = build_cache_key(
        evaluator=evaluator,
        judge_model=judge_model,
        metric=metric,
        sample_index=sample_index,
        payload=payload,
    )
    cached = await session.scalar(
        select(JudgeCacheEntry).where(JudgeCacheEntry.cache_key == cache_key)
    )
    if cached is not None:
        cached.hit_count += 1
        cached.last_accessed_at = utc_now()
        await session.commit()
        return CachedJudgment(
            score=cached.score,
            reason=cached.reason,
            details=cached.result,
            cached=True,
        )

    judged = await evaluator.evaluate(payload, metric, sample_index=sample_index)
    entry = JudgeCacheEntry(
        cache_key=cache_key,
        evaluator=evaluator.name,
        metric_name=metric.value,
        judge_model=judge_model,
        prompt_version=evaluator.prompt_version,
        score=judged.score,
        reason=judged.reason,
        result=judged.details,
    )
    session.add(entry)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(JudgeCacheEntry).where(JudgeCacheEntry.cache_key == cache_key)
        )
        if existing is None:
            raise
        existing.hit_count += 1
        await session.commit()
        return CachedJudgment(
            score=existing.score,
            reason=existing.reason,
            details=existing.result,
            cached=True,
        )
    return CachedJudgment(
        score=judged.score,
        reason=judged.reason,
        details=judged.details,
        cached=False,
    )
