from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.adapters.base import AdapterError
from app.core.config import BACKEND_ROOT, Settings
from app.providers.base import ChatMessage, ProviderChunk, ProviderError, ProviderUsage
from app.reference.corpus import corpus_text_hash
from app.reference.index import RetrievedDocument
from app.reference.target import (
    ReferenceRAGTarget,
    build_reference_index,
    extractive_answer,
    load_reference_documents,
)


class FakeIndex:
    def __init__(self, documents: list[RetrievedDocument]) -> None:
        self.documents = documents
        self.closed = False

    def search(self, _question: str, *, limit: int) -> list[RetrievedDocument]:
        return self.documents[:limit]

    def close(self) -> None:
        self.closed = True


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, *, fail: bool = False, empty: bool = False) -> None:
        self.fail = fail
        self.empty = empty
        self.closed = False

    async def stream(
        self,
        _messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        if self.fail:
            raise ProviderError("synthetic provider failure")
        if not self.empty:
            yield ProviderChunk(text=" ")
            yield ProviderChunk(text="Grounded answer.")
        yield ProviderChunk(
            text="",
            usage=ProviderUsage(input_tokens=10, output_tokens=3),
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_reference_target_streams_from_non_mock_provider() -> None:
    documents = load_reference_documents(BACKEND_ROOT / "data" / "reference_corpus.json")
    retrieved = [
        RetrievedDocument(
            id=document.id,
            title=document.title,
            category=document.category,
            text=document.text,
            score=1.0,
        )
        for document in documents[:1]
    ]
    index = FakeIndex(retrieved)
    provider = FakeProvider()
    target = ReferenceRAGTarget(
        provider=provider,  # type: ignore[arg-type]
        documents=documents,
        index=index,  # type: ignore[arg-type]
        top_k=1,
    )

    response = await target.query("How does context recall work?")
    await target.aclose()

    assert response.answer == "Grounded answer."
    assert response.ttft_source is not None
    assert response.input_tokens == 10
    assert response.output_tokens == 3
    assert provider.closed
    assert index.closed


@pytest.mark.asyncio
async def test_reference_target_reports_failures() -> None:
    documents = load_reference_documents(BACKEND_ROOT / "data" / "reference_corpus.json")
    index = FakeIndex([])
    empty = ReferenceRAGTarget(
        provider=FakeProvider(empty=True),  # type: ignore[arg-type]
        documents=documents,
        index=index,  # type: ignore[arg-type]
        top_k=1,
    )
    with pytest.raises(AdapterError, match="empty"):
        await empty.query("question")

    failing_provider = ReferenceRAGTarget(
        provider=FakeProvider(fail=True),  # type: ignore[arg-type]
        documents=documents,
        index=index,  # type: ignore[arg-type]
        top_k=1,
    )
    with pytest.raises(AdapterError, match="generation failed"):
        await failing_provider.query("question")

    class BrokenIndex(FakeIndex):
        def search(self, _question: str, *, limit: int) -> list[RetrievedDocument]:
            raise RuntimeError("index offline")

    broken = ReferenceRAGTarget(
        provider=FakeProvider(),  # type: ignore[arg-type]
        documents=documents,
        index=BrokenIndex([]),  # type: ignore[arg-type]
        top_k=1,
    )
    with pytest.raises(AdapterError, match="retrieval failed"):
        await broken.query("question")


def test_reference_builders_and_empty_extraction(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    index = build_reference_index(
        collection_name="builder",
        qdrant_url=None,
        qdrant_api_key=None,
        local_path=tmp_path / "index",
    )
    index.close()
    documents = load_reference_documents(test_settings.reference_corpus_path)
    assert corpus_text_hash(documents)
    assert extractive_answer("anything", []) == ""
