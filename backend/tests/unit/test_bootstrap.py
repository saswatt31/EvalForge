from __future__ import annotations

import pytest

from app.core.config import BACKEND_ROOT, Settings
from app.reference import bootstrap
from app.reference.corpus import load_corpus


def test_startup_bootstrap_indexes_the_bundled_corpus(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    documents = load_corpus(BACKEND_ROOT / "data" / "reference_corpus.json")
    calls: dict[str, object] = {}

    class FakeIndex:
        def ensure_indexed(self, received: object) -> None:
            calls["documents"] = received

        def close(self) -> None:
            calls["closed"] = True

    def fake_build_reference_index(**kwargs: object) -> FakeIndex:
        calls["kwargs"] = kwargs
        return FakeIndex()

    monkeypatch.setattr(bootstrap, "build_reference_index", fake_build_reference_index)
    count = bootstrap.ensure_reference_index(test_settings)

    assert count == len(documents)
    assert calls["documents"] == documents
    assert calls["closed"] is True
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["collection_name"] == test_settings.qdrant_collection


def test_startup_bootstrap_corpus_path_exists(test_settings: Settings) -> None:
    assert test_settings.reference_corpus_path.exists()
