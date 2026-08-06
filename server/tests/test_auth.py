"""
Unit tests for the API-key dependency that gates write/delete endpoints.
"""

import pytest
from src.utils.exceptions import APIKeyError


@pytest.mark.unit
class TestRequireApiKey:
    def test_raises_when_server_key_not_configured(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        from src.utils.auth import require_api_key

        with pytest.raises(APIKeyError):
            require_api_key(x_api_key="anything")

    def test_raises_when_header_missing(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret-key")
        from src.utils.auth import require_api_key

        with pytest.raises(APIKeyError):
            require_api_key(x_api_key=None)

    def test_raises_when_header_does_not_match(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret-key")
        from src.utils.auth import require_api_key

        with pytest.raises(APIKeyError):
            require_api_key(x_api_key="wrong-key")

    def test_passes_when_header_matches(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret-key")
        from src.utils.auth import require_api_key

        require_api_key(x_api_key="secret-key")
