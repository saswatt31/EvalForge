import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_api_prefix_is_normalized() -> None:
    settings = Settings(api_prefix="/api/v1/", _env_file=None)

    assert settings.api_prefix == "/api/v1"


def test_api_prefix_must_start_with_slash() -> None:
    with pytest.raises(ValidationError):
        Settings(api_prefix="api/v1", _env_file=None)


def test_blank_secrets_are_treated_as_unset() -> None:
    settings = Settings(
        _env_file=None,
        write_api_token="",
        groq_api_key=" ",
        qdrant_api_key="",
    )

    assert settings.write_api_token is None
    assert settings.groq_api_key is None
    assert settings.qdrant_api_key is None
