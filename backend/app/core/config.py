from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]

_POSTGRES_UNSAFE_QUERY_KEYS = {
    "channel_binding",
    "connection_limit",
    "pgbouncer",
    "pool_timeout",
}


def normalize_database_url(value: str) -> str:
    """Normalize local SQLite URLs and hosted Postgres URLs.

    Render, Neon, and Supabase hand out ``postgres://`` or ``postgresql://`` URLs. SQLAlchemy's
    async engine needs the ``asyncpg`` dialect, and asyncpg does not accept the libpq ``sslmode``
    query parameter. SSL is enabled separately through ``EVALFORGE_DATABASE_SSL``.
    """

    url = value.strip()
    if url.startswith("postgres://"):
        url = f"postgresql+asyncpg://{url.removeprefix('postgres://')}"
    elif url.startswith("postgresql://"):
        url = f"postgresql+asyncpg://{url.removeprefix('postgresql://')}"
    elif url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        url = f"sqlite+aiosqlite://{url.removeprefix('sqlite://')}"

    if not url.startswith("postgresql+asyncpg://"):
        return url

    base, separator, query = url.partition("?")
    if not separator:
        return url

    pairs = parse_qsl(query, keep_blank_values=True)
    normalized: list[tuple[str, str]] = []
    for key, item in pairs:
        lowered = key.lower()
        if lowered == "sslmode":
            continue
        if lowered in _POSTGRES_UNSAFE_QUERY_KEYS:
            continue
        normalized.append((key, item))
    return f"{base}?{urlencode(normalized)}" if normalized else base


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVALFORGE_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "EvalForge API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./evalforge.db"
    # Cloud Postgres providers require TLS. Set to false only for a local Postgres that does not.
    database_ssl: bool | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    write_api_token: SecretStr | None = None
    demo_mode: bool = False

    data_dir: Path = BACKEND_ROOT / "data"
    max_dataset_bytes: int = 5 * 1024 * 1024
    max_dataset_items: int = 5_000
    max_result_page_size: int = 200

    # Free-tier live-run protections. Disabled locally; enabled by deploy/render.yaml.
    live_run_protection: bool = False
    live_run_max_queries: int = Field(default=10, ge=1, le=100)
    live_run_daily_cap: int = Field(default=20, ge=1)
    live_run_per_ip_limit: int = Field(default=3, ge=1)
    live_run_rate_window_seconds: int = Field(default=3_600, ge=60)
    live_run_ip_hash_salt: SecretStr | None = None

    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_local_path: Path | None = None
    qdrant_collection: str = "evalforge_reference_v1"
    reference_index_on_startup: bool = True

    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    judge_provider: str = "groq"
    judge_model: str = "llama-3.3-70b-versatile"

    request_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    judge_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    judge_prompt_version: str = "ragas-0.4.3-v1"

    log_level: str = "INFO"

    @property
    def effective_qdrant_path(self) -> Path:
        return self.qdrant_local_path or (self.data_dir / "qdrant")

    @property
    def reference_corpus_path(self) -> Path:
        return self.data_dir / "reference_corpus.json"

    @property
    def sample_dataset_path(self) -> Path:
        return self.data_dir / "golden_dataset.jsonl"

    @property
    def qdrant_api_key_value(self) -> str | None:
        return None if self.qdrant_api_key is None else self.qdrant_api_key.get_secret_value()

    @property
    def live_run_ip_hash_salt_value(self) -> str:
        if self.live_run_ip_hash_salt is None:
            return "evalforge-live-run"
        return self.live_run_ip_hash_salt.get_secret_value()

    @field_validator(
        "write_api_token", "qdrant_api_key", "groq_api_key", "live_run_ip_hash_salt", mode="before"
    )
    @classmethod
    def blank_secret_is_none(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return None if not value.get_secret_value().strip() else value
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def database_url_is_async_compatible(cls, value: str) -> str:
        normalized = normalize_database_url(value)
        if not re.match(r"^(sqlite\+aiosqlite|postgresql\+asyncpg)://", normalized):
            raise ValueError(
                "database_url must use sqlite+aiosqlite:// or postgresql+asyncpg:// "
                "(plain sqlite://, postgres://, and postgresql:// are normalized automatically)"
            )
        return normalized

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        return value.rstrip("/")

    @field_validator("cors_origins")
    @classmethod
    def normalize_cors_origins(cls, values: list[str]) -> list[str]:
        return [value.strip().rstrip("/") for value in values if value.strip()]

    @field_validator("data_dir", "qdrant_local_path")
    @classmethod
    def resolve_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return value.expanduser().resolve()

    @model_validator(mode="after")
    def reject_wildcard_cors_in_production(self) -> Settings:
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("cors_origins cannot contain '*' in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
