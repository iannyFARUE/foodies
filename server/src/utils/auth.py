"""API-key gate for write/delete endpoints."""

import os
from typing import Optional

from fastapi import Header

from src.utils.exceptions import APIKeyError


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("API_KEY")
    if not expected or not x_api_key or x_api_key != expected:
        raise APIKeyError("Missing or invalid API key. Provide it via the 'X-API-Key' header.")
