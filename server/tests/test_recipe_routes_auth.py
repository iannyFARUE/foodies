"""
Confirms the mutating recipe endpoints are actually gated by the API-key
dependency (not just that the dependency function works in isolation).
Builds a standalone app around the recipes router so no real DB/lifespan
is needed; GET endpoints are left untouched since they don't require a key.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.routers import recipes as recipes_module
from src.utils.exceptions import APIKeyError
from src.utils.errorResponse import create_error_response

TEST_RECIPE_ID = "507f1f77bcf86cd799439011"


def make_client():
    app = FastAPI()

    @app.exception_handler(APIKeyError)
    async def _api_key_error_handler(request, exc):
        return JSONResponse(
            status_code=401,
            content=create_error_response(message=exc.message, code="INVALID_API_KEY"),
        )

    app.include_router(recipes_module.router, prefix="/api/recipes")
    return TestClient(app)


@pytest.mark.unit
class TestMutatingRoutesRequireApiKey:
    @patch('src.routers.recipes.get_collection')
    def test_create_recipe_without_api_key_is_rejected(self, mock_get_collection, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret-key")
        mock_get_collection.return_value = AsyncMock()
        client = make_client()

        response = client.post("/api/recipes/", json={"title": "Test"})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_API_KEY"
        mock_get_collection.return_value.insert_one.assert_not_called()

    @patch('src.routers.recipes.get_collection')
    def test_delete_recipe_without_api_key_is_rejected(self, mock_get_collection, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret-key")
        mock_get_collection.return_value = AsyncMock()
        client = make_client()

        response = client.delete(f"/api/recipes/{TEST_RECIPE_ID}")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_API_KEY"
        mock_get_collection.return_value.delete_one.assert_not_called()

    @patch('src.routers.recipes.get_collection')
    def test_create_recipe_with_correct_api_key_reaches_handler(self, mock_get_collection, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret-key")
        inserted_id = ObjectId()
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.acknowledged = True
        mock_result.inserted_id = inserted_id
        mock_collection.insert_one.return_value = mock_result
        mock_collection.find_one.return_value = {"_id": inserted_id, "title": "Test"}
        mock_get_collection.return_value = mock_collection
        client = make_client()

        response = client.post(
            "/api/recipes/",
            json={"title": "Test"},
            headers={"X-API-Key": "secret-key"},
        )

        assert response.status_code == 201

    @patch('src.routers.recipes.get_collection')
    def test_get_recipe_by_id_does_not_require_api_key(self, mock_get_collection, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret-key")
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Test"}
        mock_get_collection.return_value = mock_collection
        client = make_client()

        response = client.get(f"/api/recipes/{TEST_RECIPE_ID}")

        assert response.status_code == 200
