from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


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
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    write_api_token: SecretStr | None = None
    demo_mode: bool = False

    data_dir: Path = BACKEND_ROOT / "data"
    max_dataset_bytes: int = 5 * 1024 * 1024
    max_dataset_items: int = 5_000
    max_result_page_size: int = 200

    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_local_path: Path | None = None
    qdrant_collection: str = "evalforge_reference_v1"

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

    @field_validator("write_api_token", "qdrant_api_key", "groq_api_key", mode="before")
    @classmethod
    def blank_secret_is_none(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return None if not value.get_secret_value().strip() else value
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        return value.rstrip("/")

    @field_validator("data_dir", "qdrant_local_path")
    @classmethod
    def resolve_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return value.expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
