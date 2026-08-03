"""Smoke tests verifying the FastAPI app boots and is wired up correctly."""

import pytest


@pytest.mark.unit
def test_openapi_schema_generates():
    """The app should generate its OpenAPI schema without opening a database connection."""
    from main import app
    schema = app.openapi()
    assert "openapi" in schema
    assert "paths" in schema
