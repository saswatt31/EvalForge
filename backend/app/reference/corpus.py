from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReferenceDocument:
    id: str
    title: str
    category: str
    text: str


@lru_cache
def load_corpus(path: Path) -> tuple[ReferenceDocument, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        ReferenceDocument(
            id=str(item["id"]),
            title=str(item["title"]),
            category=str(item["category"]),
            text=str(item["text"]),
        )
        for item in raw
    )


def corpus_text_hash(documents: tuple[ReferenceDocument, ...]) -> str:
    import hashlib

    payload = "\n".join(
        f"{document.id}\t{document.title}\t{document.text}" for document in documents
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
