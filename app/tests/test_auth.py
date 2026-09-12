import pytest
from fastapi import HTTPException

from app.core.auth import require_api_key
from app.core.config import settings


class TestRequireApiKeyDisabled:
    """GATEWAY_API_KEYS empty (the dev default) - auth is off entirely."""

    async def test_no_key_allowed_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        result = await require_api_key(api_key=None)
        assert result == "dev"

    async def test_any_key_allowed_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        result = await require_api_key(api_key="anything-at-all")
        assert result == "dev"


class TestRequireApiKeyEnabled:
    """GATEWAY_API_KEYS set - only listed keys should pass."""

    async def test_correct_key_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "secret-key-1,secret-key-2")
        result = await require_api_key(api_key="secret-key-2")
        assert result == "secret-key-2"

    async def test_missing_key_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "secret-key-1")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key=None)
        assert exc_info.value.status_code == 401

    async def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "secret-key-1")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key="not-the-right-key")
        assert exc_info.value.status_code == 401

    async def test_key_list_is_comma_separated_and_trimmed(self, monkeypatch):
        # Real .env values often pick up stray whitespace - GATEWAY_API_KEYS
        # parsing should tolerate that rather than silently rejecting a
        # key that "looks" correct in the .env file.
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", " key-a , key-b ")
        result = await require_api_key(api_key="key-b")
        assert result == "key-b"
