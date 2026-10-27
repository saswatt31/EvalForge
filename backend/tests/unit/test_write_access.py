from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

import app.api.deps as deps
from app.core.config import Settings


async def test_write_access_is_open_without_configuration(
    monkeypatch: Any,
    test_settings: Settings,
) -> None:
    monkeypatch.setattr(deps, "get_settings", lambda: test_settings)
    await deps.require_write_access(None, None)


async def test_demo_mode_is_read_only(
    monkeypatch: Any,
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"demo_mode": True})
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as caught:
        await deps.require_write_access("secret", None)
    assert caught.value.status_code == 403


async def test_write_token_accepts_api_key_or_bearer(
    monkeypatch: Any,
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"write_api_token": SecretStr("expected-token")})
    monkeypatch.setattr(deps, "get_settings", lambda: settings)

    with pytest.raises(HTTPException) as missing:
        await deps.require_write_access(None, None)
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException):
        await deps.require_write_access("wrong-token", None)
    with pytest.raises(HTTPException):
        await deps.require_write_access(None, "Basic expected-token")

    await deps.require_write_access("expected-token", None)
    await deps.require_write_access(None, "Bearer expected-token")
