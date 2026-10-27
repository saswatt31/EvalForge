from __future__ import annotations

import hashlib
import json
import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.enums import (
    JudgeMode,
    JudgmentStatus,
    MetricName,
    QueryResultStatus,
    RunSource,
    RunStatus,
    TargetKind,
    TTFTSource,
)
from app.evaluators.base import EvaluationInput
from app.evaluators.mock import MockEvaluator
from app.reference.corpus import load_corpus
from app.reference.embedding import content_tokens
from app.reference.index import lexical_retrieve
from app.reference.target import extractive_answer
from app.schemas.dataset import DatasetImportRequest
from app.services.datasets import import_dataset
from app.storage.models import (
    DatasetVersion,
    MetricScore,
    QueryResult,
    Run,
)

DEMO_DATASET_NAME = "EvalForge synthetic reference QA"
DEMO_NOTE = (
    "Read-only demo generated from the synthetic reference corpus. "
    "Timings are simulated and judgments use the deterministic lexical mock."
)


def _stable_fraction(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


async def seed_demo_data(session: AsyncSession, settings: Settings) -> None:
    run_count = int(await session.scalar(select(func.count()).select_from(Run)) or 0)
    if run_count > 0:
        return
    sample_path = settings.sample_dataset_path
    if not sample_path.exists():
        return

    imported = await import_dataset(
        session,
        settings,
        DatasetImportRequest(
            name=DEMO_DATASET_NAME,
            description="Synthetic technical Q&A used for the offline EvalForge demo.",
            filename=sample_path.name,
            jsonl=sample_path.read_text(encoding="utf-8"),
        ),
    )
    version = await session.scalar(
        select(DatasetVersion)
        .where(DatasetVersion.id == imported.version.id)
        .options(selectinload(DatasetVersion.items))
    )
    if version is None:
        return
    items = sorted(version.items, key=lambda item: item.ordinal)
    documents = load_corpus(settings.reference_corpus_path)
    evaluator = MockEvaluator()
    now = datetime.now(UTC)

    configurations = [
        ("Synthetic demo - baseline (top-2)", 2, 360),
        ("Synthetic demo - candidate (top-6)", 6, 430),
    ]
    for run_index, (name, top_k, base_latency) in enumerate(configurations):
        run = Run(
            dataset_version_id=version.id,
            name=name,
            status=RunStatus.SUCCEEDED,
            source=RunSource.DEMO,
            target_kind=TargetKind.REFERENCE,
            provider_name="mock",
            model_name="mock-extractive-v1",
            target_config={"note": DEMO_NOTE},
            pipeline_config={"top_k": top_k, "prompt_version": "reference-rag-v1"},
            judge_mode=JudgeMode.MOCK,
            judge_model="mock-lexical-v1",
            judge_repeats=1,
            warmup_count=0,
            evaluator_config={"judge_provider": "groq"},
            config_hash=hashlib.sha256(
                json.dumps({"demo": True, "top_k": top_k}).encode("utf-8")
            ).hexdigest(),
            total_queries=len(items),
            completed_queries=len(items),
            failed_queries=0,
            started_at=now - timedelta(minutes=5) + timedelta(seconds=run_index),
            finished_at=now - timedelta(minutes=2) + timedelta(seconds=run_index),
        )
        session.add(run)
        await session.flush()

        for item in items:
            retrieved = lexical_retrieve(documents, item.question, limit=top_k)
            answer = extractive_answer(item.question, retrieved)
            contexts = [document.text for document in retrieved]
            latency = base_latency + round(_stable_fraction(f"{item.id}:{top_k}") * 320, 3)
            ttft = round(latency * (0.32 + _stable_fraction(f"ttft:{item.id}") * 0.16), 3)
            result = QueryResult(
                run_id=run.id,
                dataset_item_id=item.id,
                status=QueryResultStatus.SUCCEEDED,
                answer=answer,
                contexts=contexts,
                ttft_ms=ttft,
                ttft_source=TTFTSource.DEMO,
                latency_ms=latency,
                input_tokens=len(content_tokens(item.question + " ".join(contexts))),
                output_tokens=len(content_tokens(answer)),
                tokens_per_second=(len(content_tokens(answer)) / ((latency - ttft) / 1000))
                if latency > ttft
                else None,
            )
            session.add(result)

            payload = EvaluationInput(
                question=item.question,
                answer=answer,
                contexts=contexts,
                ground_truth=item.ground_truth,
            )
            faithfulness: list[float] = []
            for metric in (
                MetricName.CONTEXT_RECALL,
                MetricName.FAITHFULNESS,
                MetricName.ANSWER_RELEVANCE,
            ):
                judged = await evaluator.evaluate(payload, metric, sample_index=0)
                if metric is MetricName.FAITHFULNESS:
                    faithfulness.append(judged.score)
                session.add(
                    MetricScore(
                        query_result=result,
                        metric_name=metric.value,
                        sample_index=0,
                        status=JudgmentStatus.SUCCEEDED,
                        score=judged.score,
                        reason=judged.reason,
                        evaluator=evaluator.name,
                        judge_model="mock-lexical-v1",
                        prompt_version=evaluator.prompt_version,
                        judge_cached=False,
                        details={**judged.details, "demo": True},
                    )
                )
            session.add(
                MetricScore(
                    query_result=result,
                    metric_name=MetricName.HALLUCINATION_RATE.value,
                    sample_index=0,
                    status=JudgmentStatus.SUCCEEDED,
                    score=round(1 - statistics.fmean(faithfulness), 6),
                    reason="Derived as 1 minus the mean faithfulness for this answer.",
                    evaluator=evaluator.name,
                    judge_model="mock-lexical-v1",
                    prompt_version=evaluator.prompt_version,
                    judge_cached=False,
                    details={"derived_from": "faithfulness", "demo": True},
                )
            )
    await session.commit()
