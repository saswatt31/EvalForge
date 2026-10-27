from __future__ import annotations

from app.core.config import Settings
from app.providers.base import LLMProvider, ProviderError
from app.providers.groq import GroqProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider


def build_provider(
    settings: Settings,
    *,
    provider_name: str,
    model: str | None,
) -> LLMProvider:
    name = provider_name.lower()
    if name == "groq":
        if settings.groq_api_key is None:
            raise ProviderError(
                "Groq requires EVALFORGE_GROQ_API_KEY. Use provider 'mock' for a local run."
            )
        return GroqProvider(
            api_key=settings.groq_api_key.get_secret_value(),
            base_url=settings.groq_base_url,
            model=model or settings.groq_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
    if name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=model or settings.ollama_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
    if name == "mock":
        return MockProvider(model or "mock-provider-v1")
    raise ProviderError(f"Unsupported provider: {provider_name}")
