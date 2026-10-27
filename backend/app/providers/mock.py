from __future__ import annotations

from collections.abc import AsyncIterator

from app.providers.base import ChatMessage, LLMProvider, ProviderChunk


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, model: str = "mock-provider-v1") -> None:
        self.model = model

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        user_text = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        answer = f"Mock provider response for: {user_text[:160]}"
        yield ProviderChunk(text=answer)
