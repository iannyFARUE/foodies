"""Unit tests for the MongoDB client module's pure-logic helpers."""

import os
import pytest
from unittest.mock import patch


@pytest.mark.unit
def test_get_collection_returns_named_collection():
    from src.database.mongo_client import get_collection, db
    collection = get_collection("recipes")
    assert collection.name == "recipes"
    # PyMongo's __getitem__ returns a fresh wrapper object each call, so
    # compare by value (==) rather than identity (is).
    assert collection == db["recipes"]


@pytest.mark.unit
def test_voyage_ai_available_returns_none_when_unset():
    with patch.dict(os.environ, {}, clear=True):
        from src.database.mongo_client import voyage_ai_available
        assert voyage_ai_available() is None


@pytest.mark.unit
def test_voyage_ai_available_returns_none_for_placeholder_key():
    with patch.dict(os.environ, {"VOYAGE_API_KEY": "your_voyage_api_key"}):
        from src.database.mongo_client import voyage_ai_available
        assert voyage_ai_available() is None


@pytest.mark.unit
def test_voyage_ai_available_returns_key_when_configured():
    with patch.dict(os.environ, {"VOYAGE_API_KEY": "abc123"}):
        from src.database.mongo_client import voyage_ai_available
        assert voyage_ai_available() == "abc123"
