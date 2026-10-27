from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.adapters.base import AdapterError
from app.adapters.factory import build_target
from app.core.config import Settings
from app.core.enums import JudgeMode
from app.core.errors import (
    ConflictError,
    EvalForgeError,
    ExternalServiceError,
    InvalidDatasetError,
    NotFoundError,
    ReadOnlyError,
    RunStateError,
    UnauthorizedError,
)
from app.core.logging import configure_logging
from app.evaluators import build_evaluator
from app.evaluators.base import EvaluatorError
from app.evaluators.mock import MockEvaluator
from app.evaluators.ragas import RagasEvaluator
from app.providers.base import ProviderError
from app.providers.factory import build_provider


def test_provider_factory_selects_mock_and_rejects_unknown(test_settings: Settings) -> None:
    provider = build_provider(test_settings, provider_name="mock", model=None)
    assert provider.name == "mock"
    with pytest.raises(ProviderError, match="Unsupported"):
        build_provider(test_settings, provider_name="unknown", model=None)


def test_groq_provider_requires_key(test_settings: Settings) -> None:
    with pytest.raises(ProviderError, match="GROQ_API_KEY"):
        build_provider(test_settings, provider_name="groq", model=None)


def test_target_factory_rejects_invalid_configuration(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    with pytest.raises(AdapterError, match="http"):
        build_target(
            test_settings,
            target_kind="http",
            provider_name="custom",
            model_name=None,
            target_config={},
            pipeline_config={},
        )
    with pytest.raises(AdapterError, match="top_k"):
        build_target(
            test_settings,
            target_kind="reference",
            provider_name="mock",
            model_name=None,
            target_config={},
            pipeline_config={"top_k": 99},
        )
    with pytest.raises(AdapterError, match="Unknown"):
        build_target(
            test_settings,
            target_kind="websocket",
            provider_name="custom",
            model_name=None,
            target_config={},
            pipeline_config={},
        )


def test_target_factory_builds_http_target(test_settings: Settings) -> None:
    target = build_target(
        test_settings,
        target_kind="http",
        provider_name="custom",
        model_name=None,
        target_config={"url": "https://example.test/query", "streaming": True},
        pipeline_config={},
    )
    assert target.name == "http"


def test_evaluator_factory_and_ragas_configuration(test_settings: Settings) -> None:
    evaluator = build_evaluator(
        test_settings,
        judge_mode=JudgeMode.MOCK,
        judge_model="mock",
        evaluator_config={},
    )
    assert isinstance(evaluator, MockEvaluator)
    with pytest.raises(EvaluatorError, match="GROQ_API_KEY"):
        build_evaluator(
            test_settings,
            judge_mode=JudgeMode.LLM,
            judge_model="judge",
            evaluator_config={"judge_provider": "groq"},
        )
    with pytest.raises(EvaluatorError, match="Unsupported judge"):
        RagasEvaluator(test_settings, judge_provider="unknown", judge_model="judge")


def test_application_error_taxonomy() -> None:
    base = EvalForgeError("problem", details={"field": "x"})
    assert base.status_code == 400
    assert base.details == {"field": "x"}
    assert NotFoundError.status_code == 404
    assert ConflictError.status_code == 409
    assert InvalidDatasetError.status_code == 422
    assert ReadOnlyError.status_code == 403
    assert UnauthorizedError.status_code == 401
    assert RunStateError.status_code == 409
    assert ExternalServiceError.status_code == 502


def test_configure_logging_sets_level() -> None:
    configure_logging("debug")
    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
