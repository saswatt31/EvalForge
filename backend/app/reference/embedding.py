from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

from ragas.embeddings import BaseRagasEmbedding

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_'-]*")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def content_tokens(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOP_WORDS and len(token) > 1
    ]


def _hash(token: str) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % 384, 1.0 if value & 1 else -1.0


class HashEmbedding(BaseRagasEmbedding):
    """Deterministic local feature-hashing embedding.

    This keeps the demo and tests offline. It is lexical, not a trained semantic model, and is
    recorded in pipeline metadata so scores are never confused with embedding-model quality.
    """

    name = "evalforge-hash-384-v1"
    dimensions = 384

    def embed_text(self, text: str, **kwargs: object) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = content_tokens(text)
        features = tokens + [
            f"{tokens[index]}::{tokens[index + 1]}" for index in range(max(0, len(tokens) - 1))
        ]
        for feature in features:
            index, sign = _hash(feature)
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    async def aembed_text(self, text: str, **kwargs: object) -> list[float]:
        return self.embed_text(text)

    def embed_texts(self, texts: list[str], **kwargs: object) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


def lexical_overlap(left: str, right: str) -> float:
    left_tokens = set(content_tokens(left))
    right_tokens = set(content_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def supported_fraction(answer: str, contexts: Iterable[str]) -> float:
    answer_tokens = content_tokens(answer)
    if not answer_tokens:
        return 0.0
    evidence = set(content_tokens(" ".join(contexts)))
    if not evidence:
        return 0.0
    return sum(token in evidence for token in answer_tokens) / len(answer_tokens)
