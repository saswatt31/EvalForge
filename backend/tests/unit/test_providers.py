from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.providers.base import ChatMessage, ProviderError
from app.providers.groq import GroqProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider


async def test_groq_streams_text_and_usage() -> None:
    events = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":2}}',
        "data: [DONE]",
        "",
    ]
    requested: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        requested["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            text="\n".join(events),
            headers={"content-type": "text/event-stream"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(
        api_key="test",
        base_url="https://groq.test/v1",
        model="test-model",
        timeout_seconds=5,
        client=client,
    )
    chunks = [chunk async for chunk in provider.stream([ChatMessage(role="user", content="Hi")])]

    assert "".join(chunk.text for chunk in chunks) == "Hello"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 7
    assert requested["body"]["stream"] is True
    await client.aclose()


async def test_groq_reports_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(
        api_key="test",
        base_url="https://groq.test/v1",
        model="test-model",
        timeout_seconds=5,
        client=client,
    )
    with pytest.raises(ProviderError, match="HTTP 429"):
        async for _ in provider.stream([ChatMessage(role="user", content="Hi")]):
            pass
    await client.aclose()


async def test_ollama_streams_ndjson() -> None:
    lines = [
        {"message": {"content": "Hello"}, "done": False},
        {
            "message": {"content": " world"},
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 2,
        },
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="\n".join(json.dumps(line) for line in lines),
            headers={"content-type": "application/x-ndjson"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="test-model",
        timeout_seconds=5,
        client=client,
    )
    chunks = [chunk async for chunk in provider.stream([ChatMessage(role="user", content="Hi")])]

    assert "".join(chunk.text for chunk in chunks) == "Hello world"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.output_tokens == 2
    await client.aclose()


async def test_mock_provider_complete() -> None:
    provider = MockProvider()
    answer = await provider.complete([ChatMessage(role="user", content="Question")])
    assert answer.startswith("Mock provider response for: Question")
