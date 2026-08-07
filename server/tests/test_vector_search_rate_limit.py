"""
Confirms GET /api/recipes/vector-search is actually gated by the rate
limiter (not just that InMemoryRateLimiter works in isolation). Builds a
standalone app around the recipes router so no real DB/Voyage call happens;
each mutating dependency (embedding, DB aggregation) is mocked.
"""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.routers import recipes as recipes_module
from src.utils.exceptions import RateLimitExceededError
from src.utils.errorResponse import create_error_response


def make_client():
    app = FastAPI()

    @app.exception_handler(RateLimitExceededError)
    async def _rate_limit_handler(request, exc):
        return JSONResponse(
            status_code=429,
            content=create_error_response(message=exc.message, code="RATE_LIMIT_EXCEEDED"),
        )

    app.include_router(recipes_module.router, prefix="/api/recipes")
    return TestClient(app)


@pytest.fixture(autouse=True)
def small_limit_and_clean_state(monkeypatch):
    monkeypatch.setattr(recipes_module.VECTOR_SEARCH_RATE_LIMIT, "max_requests", 2)
    recipes_module.VECTOR_SEARCH_RATE_LIMIT._hits.clear()
    yield
    recipes_module.VECTOR_SEARCH_RATE_LIMIT._hits.clear()


@pytest.mark.unit
class TestVectorSearchRateLimit:
    @patch('src.routers.recipes.execute_aggregation_on_collection')
    @patch('src.routers.recipes.get_embedding')
    @patch('src.routers.recipes.voyage_ai_available')
    @patch('src.routers.recipes.get_collection')
    def test_allows_requests_up_to_the_limit(
        self, mock_get_collection, mock_available, mock_get_embedding, mock_execute_aggregation
    ):
        mock_available.return_value = "fake-key"
        mock_get_embedding.return_value = [0.1] * 2048
        mock_execute_aggregation.return_value = []
        client = make_client()

        for _ in range(2):
            response = client.get("/api/recipes/vector-search?q=garlicky+pasta")
            assert response.status_code == 200

    @patch('src.routers.recipes.execute_aggregation_on_collection')
    @patch('src.routers.recipes.get_embedding')
    @patch('src.routers.recipes.voyage_ai_available')
    @patch('src.routers.recipes.get_collection')
    def test_rejects_requests_beyond_the_limit(
        self, mock_get_collection, mock_available, mock_get_embedding, mock_execute_aggregation
    ):
        mock_available.return_value = "fake-key"
        mock_get_embedding.return_value = [0.1] * 2048
        mock_execute_aggregation.return_value = []
        client = make_client()

        for _ in range(2):
            client.get("/api/recipes/vector-search?q=garlicky+pasta")
        response = client.get("/api/recipes/vector-search?q=garlicky+pasta")

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        mock_get_embedding.assert_called()
