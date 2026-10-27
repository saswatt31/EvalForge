from __future__ import annotations

from typing import Any

from app.adapters.base import AdapterError, RAGTarget
from app.adapters.http import HttpRAGTarget
from app.core.config import Settings
from app.providers.factory import build_provider
from app.reference.corpus import load_corpus
from app.reference.target import ReferenceRAGTarget, build_reference_index


def build_target(
    settings: Settings,
    *,
    target_kind: str,
    provider_name: str,
    model_name: str | None,
    target_config: dict[str, Any],
    pipeline_config: dict[str, Any],
) -> RAGTarget:
    if target_kind == "http":
        url = target_config.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise AdapterError("HTTP target requires an http(s) URL")
        headers = target_config.get("headers") or {}
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
        ):
            raise AdapterError("Target headers must be a string dictionary")
        return HttpRAGTarget(
            url=url,
            streaming=bool(target_config.get("streaming", False)),
            timeout_seconds=float(target_config.get("timeout_seconds", 60)),
            headers=headers,
        )

    if target_kind != "reference":
        raise AdapterError(f"Unknown target kind: {target_kind}")

    top_k = int(pipeline_config.get("top_k", 5))
    if top_k < 1 or top_k > 20:
        raise AdapterError("top_k must be between 1 and 20")

    provider = build_provider(
        settings,
        provider_name=provider_name,
        model=model_name,
    )
    documents = load_corpus(settings.reference_corpus_path)
    index = build_reference_index(
        collection_name=settings.qdrant_collection,
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        local_path=settings.effective_qdrant_path,
    )
    try:
        index.ensure_indexed(documents)
    except Exception:
        index.close()
        raise

    return ReferenceRAGTarget(
        provider=provider,
        documents=documents,
        index=index,
        top_k=top_k,
        prompt_version=str(pipeline_config.get("prompt_version", "reference-rag-v1")),
    )
