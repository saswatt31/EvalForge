import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    JudgeMode,
    JudgmentStatus,
    QueryResultStatus,
    RunSource,
    TargetKind,
    TTFTSource,
)
from app.storage.models import (
    Dataset,
    DatasetItem,
    DatasetVersion,
    JudgeCacheEntry,
    MetricScore,
    QueryResult,
    Run,
)


def build_run() -> tuple[Dataset, Run]:
    dataset = Dataset(name="Sample docs", description="Small fixture dataset")
    version = DatasetVersion(
        dataset=dataset,
        version_number=1,
        content_hash="a" * 64,
        source_filename="sample.jsonl",
        item_count=1,
    )
    item = DatasetItem(
        dataset_version=version,
        ordinal=0,
        question="What is RAG?",
        ground_truth="Retrieval augmented generation.",
        reference_contexts=["RAG retrieves documents before generating."],
    )
    run = Run(
        dataset_version=version,
        name="baseline",
        source=RunSource.CLI,
        target_kind=TargetKind.REFERENCE,
        provider_name="groq",
        model_name="llama-test",
        target_config={"kind": "reference"},
        pipeline_config={"chunk_size": 512, "top_k": 5},
        judge_mode=JudgeMode.MOCK,
        judge_model="mock",
        judge_repeats=1,
        evaluator_config={"prompt_version": "v1"},
        config_hash="b" * 64,
        total_queries=1,
        completed_queries=1,
    )
    result = QueryResult(
        run=run,
        dataset_item=item,
        status=QueryResultStatus.SUCCEEDED,
        answer="RAG combines retrieval with generation.",
        contexts=["RAG retrieves documents before generating."],
        ttft_ms=120.5,
        ttft_source=TTFTSource.MEASURED,
        latency_ms=480.0,
        input_tokens=20,
        output_tokens=8,
        tokens_per_second=22.3,
    )
    MetricScore(
        query_result=result,
        metric_name="faithfulness",
        sample_index=0,
        status=JudgmentStatus.SUCCEEDED,
        score=0.95,
        reason="Claims are supported by the context.",
        evaluator="ragas",
        judge_model="mock",
        prompt_version="v1",
    )
    return dataset, run


async def test_models_persist_relationships_and_defaults(db_session: AsyncSession) -> None:
    dataset, run = build_run()
    db_session.add_all([dataset, run])
    await db_session.commit()

    assert run.id is not None
    assert run.status.value == "queued"
    assert run.created_at is not None
    assert run.updated_at is not None
    assert await db_session.scalar(select(func.count()).select_from(Dataset)) == 1
    assert await db_session.scalar(select(func.count()).select_from(DatasetVersion)) == 1
    assert await db_session.scalar(select(func.count()).select_from(DatasetItem)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Run)) == 1
    assert await db_session.scalar(select(func.count()).select_from(QueryResult)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MetricScore)) == 1


async def test_judge_cache_entry_persists(db_session: AsyncSession) -> None:
    entry = JudgeCacheEntry(
        cache_key="c" * 64,
        evaluator="ragas",
        metric_name="faithfulness",
        judge_model="mock",
        prompt_version="v1",
        score=0.9,
        result={"score": 0.9},
    )
    db_session.add(entry)
    await db_session.commit()

    assert entry.id is not None
    assert entry.hit_count == 0
    assert entry.last_accessed_at is not None


async def test_ttft_provenance_constraint_rejects_ambiguous_value(
    db_session: AsyncSession,
) -> None:
    dataset, run = build_run()
    result = run.query_results[0]
    result.ttft_source = None
    db_session.add_all([dataset, run])

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()
