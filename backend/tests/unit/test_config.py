import pytest
from pydantic import ValidationError

from app.core.config import Settings, normalize_database_url


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgres://user:pass@db.example.com:5432/evalforge",
            "postgresql+asyncpg://user:pass@db.example.com:5432/evalforge",
        ),
        (
            "postgresql://user:pass@db.example.com/evalforge?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://user:pass@db.example.com/evalforge",
        ),
        (
            "postgresql+asyncpg://user:pass@db.example.com/evalforge?sslmode=verify-full&application_name=evalforge",
            "postgresql+asyncpg://user:pass@db.example.com/evalforge?application_name=evalforge",
        ),
        (
            "sqlite:///./local.db",
            "sqlite+aiosqlite:///./local.db",
        ),
        (
            "sqlite+aiosqlite:////data/evalforge.db",
            "sqlite+aiosqlite:////data/evalforge.db",
        ),
    ],
)
def test_database_url_switches_between_sqlite_and_postgres(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected
    assert Settings(_env_file=None, database_url=raw).database_url == expected


def test_unsupported_database_scheme_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="mysql://localhost/evalforge")


def test_production_cors_must_not_be_wildcard() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            cors_origins=["*"],
        )


def test_cors_origins_are_normalized() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins=[" https://evalforge.vercel.app/ ", ""],
    )
    assert settings.cors_origins == ["https://evalforge.vercel.app"]
