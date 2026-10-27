from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.adapters.base import AdapterError, RAGTarget, TargetResponse, tokens_per_second
from app.core.enums import TTFTSource


class HttpRAGTarget(RAGTarget):
    name = "http"

    def __init__(
        self,
        *,
        url: str,
        streaming: bool,
        timeout_seconds: float,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url
        self._streaming = streaming
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0)
        )
        self._headers = headers or {}
        self._owns_client = client is None

    async def query(self, question: str) -> TargetResponse:
        if self._streaming:
            return await self._streaming_query(question)
        return await self._json_query(question)

    async def _json_query(self, question: str) -> TargetResponse:
        started = time.perf_counter()
        try:
            response = await self._client.post(
                self._url,
                json={"question": question},
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise AdapterError(f"Target request failed: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            raise AdapterError(
                f"Target returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AdapterError("Target response was not valid JSON") from exc

        return _parse_json_payload(payload, latency_ms=latency_ms)

    async def _streaming_query(self, question: str) -> TargetResponse:
        headers = {**self._headers, "Accept": "text/event-stream"}
        started = time.perf_counter()
        first_token_at: float | None = None
        chunks: list[str] = []
        contexts: list[str] = []
        input_tokens: int | None = None
        output_tokens: int | None = None

        try:
            async with self._client.stream(
                "POST",
                self._url,
                json={"question": question},
                headers=headers,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")[:300]
                    raise AdapterError(f"Target returned HTTP {response.status_code}: {body}")
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raw = b"".join([chunk async for chunk in response.aiter_bytes()])
                    latency_ms = (time.perf_counter() - started) * 1000
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise AdapterError("Streaming target did not return SSE or JSON") from exc
                    return _parse_json_payload(payload, latency_ms=latency_ms)

                async for data in _iter_sse_data(response):
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise AdapterError("Target returned malformed SSE JSON") from exc
                    event_name = event.get("event")
                    if event_name == "error" or "error" in event:
                        raise AdapterError(f"Target stream error: {event.get('error')}")
                    if "contexts" in event:
                        contexts = _valid_contexts(event["contexts"])
                    delta = event.get("delta") or event.get("token") or ""
                    if isinstance(delta, str) and delta:
                        if first_token_at is None and delta.strip():
                            first_token_at = time.perf_counter()
                        chunks.append(delta)
                    if "input_tokens" in event:
                        input_tokens = _optional_int(event["input_tokens"])
                    if "output_tokens" in event:
                        output_tokens = _optional_int(event["output_tokens"])
        except httpx.HTTPError as exc:
            raise AdapterError(f"Target stream failed: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        answer = "".join(chunks).strip()
        if not answer:
            raise AdapterError("Target stream completed without an answer")
        ttft_ms = (first_token_at - started) * 1000 if first_token_at is not None else None
        return TargetResponse(
            answer=answer,
            contexts=contexts,
            latency_ms=round(latency_ms, 3),
            ttft_ms=round(ttft_ms, 3) if ttft_ms is not None else None,
            ttft_source=TTFTSource.MEASURED if ttft_ms is not None else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_per_second=tokens_per_second(
                latency_ms=latency_ms,
                ttft_ms=ttft_ms,
                output_tokens=output_tokens,
            ),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


async def _iter_sse_data(response: httpx.Response) -> AsyncIterator[str]:
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield "\n".join(data_lines)


def _parse_json_payload(payload: Any, *, latency_ms: float) -> TargetResponse:
    if not isinstance(payload, dict):
        raise AdapterError("Target JSON response must be an object")
    answer = payload.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise AdapterError("Target JSON response is missing a non-empty answer")
    contexts = _valid_contexts(payload.get("contexts", []))

    ttft_value = payload.get("ttft_ms")
    ttft_ms = _optional_float(ttft_value)
    if ttft_ms is not None and ttft_ms > latency_ms + 5:
        raise AdapterError("Target-reported TTFT exceeds measured wall-clock latency")
    input_tokens = _optional_int(payload.get("input_tokens"))
    output_tokens = _optional_int(payload.get("output_tokens"))
    return TargetResponse(
        answer=answer.strip(),
        contexts=contexts,
        latency_ms=round(latency_ms, 3),
        ttft_ms=ttft_ms,
        ttft_source=TTFTSource.TARGET_REPORTED if ttft_ms is not None else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tokens_per_second=tokens_per_second(
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            output_tokens=output_tokens,
        ),
    )


def _valid_contexts(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AdapterError("Target contexts must be a JSON array of strings")
    return [item.strip() for item in value if item.strip()]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AdapterError("Expected a numeric value from target")
    if value < 0:
        raise AdapterError("Target numeric values cannot be negative")
    return round(float(value), 3)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AdapterError("Expected an integer token count from target")
    if value < 0:
        raise AdapterError("Target token counts cannot be negative")
    return int(value)
