"""
Unit Tests for Recipe Routes

These tests verify route handler logic using mocked MongoDB operations
(unittest.mock.AsyncMock), with no real database connection required.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi.responses import JSONResponse

TEST_RECIPE_ID = "507f1f77bcf86cd799439011"
INVALID_RECIPE_ID = "invalid-id"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetRecipeById:
    """Tests for GET /api/recipes/{id} endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_get_recipe_by_id_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_recipe = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Test Recipe", "cuisine": "Italian"}
        mock_collection.find_one.return_value = mock_recipe
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_recipe_by_id
        result = await get_recipe_by_id(TEST_RECIPE_ID)

        assert result.success is True
        assert result.data["title"] == "Test Recipe"
        assert result.data["_id"] == TEST_RECIPE_ID
        mock_collection.find_one.assert_called_once_with({"_id": ObjectId(TEST_RECIPE_ID)})

    @patch('src.routers.recipes.get_collection')
    async def test_get_recipe_by_id_not_found(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_recipe_by_id
        response = await get_recipe_by_id(TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["success"] is False
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_get_recipe_by_id_invalid_id(self):
        from src.routers.recipes import get_recipe_by_id
        response = await get_recipe_by_id(INVALID_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"

    @patch('src.routers.recipes.get_collection')
    async def test_get_recipe_by_id_database_error(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = Exception("Database connection failed")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_recipe_by_id
        response = await get_recipe_by_id(TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "DATABASE_ERROR"
