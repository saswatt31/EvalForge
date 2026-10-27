from app.core.config import Settings
from app.core.enums import JudgeMode
from app.evaluators.base import EvaluationInput, Evaluator, JudgeResult
from app.evaluators.mock import MockEvaluator
from app.evaluators.ragas import RagasEvaluator

__all__ = [
    "EvaluationInput",
    "Evaluator",
    "JudgeResult",
    "MockEvaluator",
    "RagasEvaluator",
    "build_evaluator",
]


def build_evaluator(
    settings: Settings,
    *,
    judge_mode: JudgeMode,
    judge_model: str,
    evaluator_config: dict[str, object],
) -> Evaluator:
    if judge_mode is JudgeMode.MOCK:
        return MockEvaluator()
    return RagasEvaluator(
        settings,
        judge_provider=str(evaluator_config.get("judge_provider", settings.judge_provider)),
        judge_model=judge_model,
    )
