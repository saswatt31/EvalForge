from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import BACKEND_ROOT
from app.providers.mock import MockProvider
from app.reference.corpus import load_corpus
from app.reference.embedding import HashEmbedding, lexical_overlap
from app.reference.index import QdrantReferenceIndex, lexical_retrieve
from app.reference.target import ReferenceRAGTarget, extractive_answer


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    embedding = HashEmbedding()
    first = embedding.embed_text("TTFT measures time to first token")
    second = embedding.embed_text("TTFT measures time to first token")

    assert first == second
    assert len(first) == embedding.dimensions
    assert abs(sum(value * value for value in first) - 1) < 1e-6
    assert embedding.embed_texts(["one", "two"])[0] == embedding.embed_text("one")


def test_lexical_retrieval_prefers_matching_document() -> None:
    documents = load_corpus(BACKEND_ROOT / "data" / "reference_corpus.json")
    results = lexical_retrieve(documents, "How does context recall work?", limit=3)
    assert len(results) == 3
    assert results[0].score >= results[1].score
    assert lexical_overlap("context recall", "Context recall measures coverage") > 0


@pytest.mark.integration
async def test_qdrant_index_round_trip(tmp_path: Path) -> None:
    documents = load_corpus(BACKEND_ROOT / "data" / "reference_corpus.json")
    index = QdrantReferenceIndex(
        collection_name="reference_test",
        qdrant_url=None,
        qdrant_api_key=None,
        local_path=tmp_path / "qdrant",
    )
    index.ensure_indexed(documents)
    index.ensure_indexed(documents)
    results = index.search("How does context recall work?", limit=3)
    index.close()

    assert len(results) == 3
    assert all(document.text for document in results)
    assert results[0].score >= results[1].score


async def test_reference_target_with_mock_provider(tmp_path: Path) -> None:
    documents = load_corpus(BACKEND_ROOT / "data" / "reference_corpus.json")
    index = QdrantReferenceIndex(
        collection_name="reference_target_test",
        qdrant_url=None,
        qdrant_api_key=None,
        local_path=tmp_path / "qdrant-target",
    )
    index.ensure_indexed(documents)
    target = ReferenceRAGTarget(
        provider=MockProvider(),
        documents=documents,
        index=index,
        top_k=3,
    )
    response = await target.query("How does context recall work?")
    await target.aclose()

    assert response.answer
    assert len(response.contexts) == 3
    assert response.latency_ms >= 0
    assert response.ttft_ms is None


def test_extractive_answer_returns_evidence_sentence() -> None:
    documents = load_corpus(BACKEND_ROOT / "data" / "reference_corpus.json")
    retrieved = lexical_retrieve(documents, "How does context recall work?", limit=2)
    answer = extractive_answer("How does context recall work?", retrieved)
    assert "context recall" in answer.lower()


def test_ensure_indexed_is_idempotent_when_collection_is_complete(tmp_path: Path) -> None:
    documents = load_corpus(BACKEND_ROOT / "data" / "reference_corpus.json")
    index = QdrantReferenceIndex(
        collection_name="idempotent_test",
        qdrant_url=None,
        qdrant_api_key=None,
        local_path=tmp_path / "qdrant-idempotent",
    )
    index.client.close()

    calls: list[str] = []

    class CompleteCollectionClient:
        def collection_exists(self, _name: str) -> bool:
            calls.append("exists")
            return True

        def count(self, _name: str, *, exact: bool) -> SimpleNamespace:
            assert exact is True
            calls.append("count")
            return SimpleNamespace(count=len(documents))

        def delete_collection(self, _name: str) -> None:
            raise AssertionError("a complete collection must not be deleted")

        def create_collection(self, **_kwargs: object) -> None:
            raise AssertionError("a complete collection must not be recreated")

        def upsert(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("a complete collection must not be re-upserted")

        def close(self) -> None:
            calls.append("close")

    index.client = CompleteCollectionClient()  # type: ignore[assignment]
    index.ensure_indexed(documents)
    index.close()

    assert calls == ["exists", "count", "close"]
