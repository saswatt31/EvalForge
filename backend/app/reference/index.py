from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.reference.corpus import ReferenceDocument
from app.reference.embedding import HashEmbedding

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    id: str
    title: str
    category: str
    text: str
    score: float


class QdrantReferenceIndex:
    def __init__(
        self,
        *,
        collection_name: str,
        qdrant_url: str | None,
        qdrant_api_key: str | None,
        local_path: Path,
        embedding: HashEmbedding | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding = embedding or HashEmbedding()
        if qdrant_url:
            self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=30)
        else:
            local_path.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(local_path))

    def ensure_indexed(self, documents: tuple[ReferenceDocument, ...]) -> None:
        if len(documents) == 0:
            raise ValueError("Reference corpus is empty")
        exists = self.client.collection_exists(self.collection_name)
        if exists:
            count = self.client.count(self.collection_name, exact=True).count
            if count == len(documents):
                return
            self.client.delete_collection(self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.embedding.dimensions,
                distance=Distance.COSINE,
            ),
        )
        points = [
            PointStruct(
                id=index,
                vector=self.embedding.embed_text(document.text),
                payload={
                    "document_id": document.id,
                    "title": document.title,
                    "category": document.category,
                    "text": document.text,
                },
            )
            for index, document in enumerate(documents)
        ]
        self.client.upsert(self.collection_name, points=points)
        logger.info("Indexed %d reference documents in Qdrant", len(points))

    def search(self, question: str, *, limit: int) -> list[RetrievedDocument]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=self.embedding.embed_text(question),
            limit=limit,
            with_payload=True,
        )
        results: list[RetrievedDocument] = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                RetrievedDocument(
                    id=str(payload.get("document_id", point.id)),
                    title=str(payload.get("title", "")),
                    category=str(payload.get("category", "")),
                    text=str(payload.get("text", "")),
                    score=float(point.score),
                )
            )
        return results

    def close(self) -> None:
        self.client.close()


def lexical_retrieve(
    documents: tuple[ReferenceDocument, ...],
    question: str,
    *,
    limit: int,
) -> list[RetrievedDocument]:
    from app.reference.embedding import lexical_overlap

    ranked = [
        RetrievedDocument(
            id=document.id,
            title=document.title,
            category=document.category,
            text=document.text,
            score=lexical_overlap(question, document.text),
        )
        for document in documents
    ]
    return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]
