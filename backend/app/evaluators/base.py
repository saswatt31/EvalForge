from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import MetricName


class EvaluatorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str


@dataclass(frozen=True, slots=True)
class JudgeResult:
    metric: MetricName
    score: float
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


class Evaluator(ABC):
    name: str
    version: str
    prompt_version: str

    @abstractmethod
    async def evaluate(
        self,
        payload: EvaluationInput,
        metric: MetricName,
        *,
        sample_index: int,
    ) -> JudgeResult:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None
