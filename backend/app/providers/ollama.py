from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import (
    ChatMessage,
    LLMProvider,
    ProviderChunk,
    ProviderError,
    ProviderUsage,
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0)
        )
        self._owns_client = client is None

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        options: dict[str, object] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        payload = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": True,
            "options": options,
        }

        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")[:500]
                    raise ProviderError(f"Ollama returned HTTP {response.status_code}: {body}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ProviderError("Ollama returned malformed NDJSON") from exc
                    text = event.get("message", {}).get("content") or ""
                    usage = None
                    if event.get("done"):
                        usage = ProviderUsage(
                            input_tokens=event.get("prompt_eval_count"),
                            output_tokens=event.get("eval_count"),
                        )
                    if text or usage:
                        yield ProviderChunk(text=text, usage=usage)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
