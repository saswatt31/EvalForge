from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.reference.corpus import load_corpus
from app.reference.target import build_reference_index

logger = logging.getLogger(__name__)


def ensure_reference_index(settings: Settings) -> int:
    """Create and populate the reference collection if it is empty.

    ``QdrantReferenceIndex.ensure_indexed`` is idempotent: when the collection already contains the
    expected number of points it returns without rewriting anything. Startup calls therefore cost
    one count query per boot.
    """

    documents = load_corpus(settings.reference_corpus_path)
    index = build_reference_index(
        collection_name=settings.qdrant_collection,
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key_value,
        local_path=settings.effective_qdrant_path,
    )
    try:
        index.ensure_indexed(documents)
    finally:
        index.close()
    logger.info(
        "Reference index ready: collection=%s documents=%d",
        settings.qdrant_collection,
        len(documents),
    )
    return len(documents)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ensure_reference_index(settings)


if __name__ == "__main__":
    main()
