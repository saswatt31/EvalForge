from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.enums import TTFTSource


@dataclass(frozen=True, slots=True)
class TargetResponse:
    answer: str
    contexts: list[str]
    latency_ms: float
    ttft_ms: float | None
    ttft_source: TTFTSource | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None


class AdapterError(RuntimeError):
    pass


class RAGTarget(ABC):
    name: str

    @abstractmethod
    async def query(self, question: str) -> TargetResponse:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


def tokens_per_second(
    *,
    latency_ms: float,
    ttft_ms: float | None,
    output_tokens: int | None,
) -> float | None:
    if output_tokens is None or output_tokens < 0:
        return None
    if ttft_ms is None:
        return None
    generation_window_seconds = (latency_ms - ttft_ms) / 1000
    if generation_window_seconds <= 0:
        return None
    return output_tokens / generation_window_seconds
