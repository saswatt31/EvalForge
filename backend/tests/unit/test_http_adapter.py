from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.base import AdapterError
from app.adapters.http import HttpRAGTarget
from app.core.enums import TTFTSource


async def test_json_target_parses_metrics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"question": "What is Qdrant?"}
        return httpx.Response(
            200,
            json={
                "answer": "A vector database.",
                "contexts": ["Qdrant stores vectors."],
                "ttft_ms": 0.01,
                "input_tokens": 12,
                "output_tokens": 4,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    target = HttpRAGTarget(
        url="https://target.test/query",
        streaming=False,
        timeout_seconds=5,
        client=client,
    )
    result = await target.query("What is Qdrant?")

    assert result.answer == "A vector database."
    assert result.contexts == ["Qdrant stores vectors."]
    assert result.ttft_source is TTFTSource.TARGET_REPORTED
    assert result.ttft_ms == 0.01
    assert result.tokens_per_second is not None
    await client.aclose()


async def test_sse_target_uses_first_content_delta_for_ttft() -> None:
    body = "\n".join(
        [
            'data: {"event":"contexts","contexts":["Doc one","Doc two"]}',
            "",
            'data: {"event":"token","delta":"Answer"}',
            "",
            'data: {"event":"token","delta":" text"}',
            "",
            'data: {"event":"done","input_tokens":9,"output_tokens":3}',
            "",
        ]
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=body,
            headers={"content-type": "text/event-stream; charset=utf-8"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    target = HttpRAGTarget(
        url="https://target.test/stream",
        streaming=True,
        timeout_seconds=5,
        client=client,
    )
    result = await target.query("Question")

    assert result.answer == "Answer text"
    assert result.contexts == ["Doc one", "Doc two"]
    assert result.ttft_source is TTFTSource.MEASURED
    assert result.ttft_ms is not None
    assert result.output_tokens == 3
    await client.aclose()


async def test_streaming_target_accepts_json_fallback() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"answer": "JSON answer", "contexts": []},
            headers={"content-type": "application/json"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    target = HttpRAGTarget(
        url="https://target.test/query",
        streaming=True,
        timeout_seconds=5,
        client=client,
    )
    result = await target.query("Question")
    assert result.answer == "JSON answer"
    assert result.ttft_ms is None
    assert result.ttft_source is None
    await client.aclose()


async def test_json_target_rejects_impossible_ttft() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"answer": "Answer", "contexts": [], "ttft_ms": 60_000},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    target = HttpRAGTarget(
        url="https://target.test/query",
        streaming=False,
        timeout_seconds=5,
        client=client,
    )
    with pytest.raises(AdapterError, match="TTFT exceeds"):
        await target.query("Question")
    await client.aclose()


async def test_streaming_target_rejects_silent_stream() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='data: {"event":"contexts","contexts":["Doc"]}\n\n',
            headers={"content-type": "text/event-stream"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    target = HttpRAGTarget(
        url="https://target.test/stream",
        streaming=True,
        timeout_seconds=5,
        client=client,
    )
    with pytest.raises(AdapterError, match="without an answer"):
        await target.query("Question")
    await client.aclose()
