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


class _AsyncCursorStub:
    """
    Minimal stand-in for a pymongo cursor: .sort()/.skip()/.limit() are
    synchronous chain calls (like the real driver), but iteration is async.
    Deliberately not a MagicMock — configuring __aiter__/__anext__ on Mock
    objects to behave correctly is version-sensitive, so a small real class
    is the reliable way to fake this protocol.
    """

    def __init__(self, items):
        self._iter = iter(items)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetAllRecipes:
    """Tests for GET /api/recipes/ endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_get_all_recipes_returns_list(self, mock_get_collection):
        mock_collection = MagicMock()
        recipes = [
            {"_id": ObjectId(TEST_RECIPE_ID), "title": "Recipe A", "cuisine": "Italian"},
            {"_id": ObjectId("507f1f77bcf86cd799439012"), "title": "Recipe B", "cuisine": "Mexican"},
        ]
        mock_collection.find.return_value = _AsyncCursorStub(recipes)
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_all_recipes
        result = await get_all_recipes()

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0]["_id"] == TEST_RECIPE_ID

    @patch('src.routers.recipes.get_collection')
    async def test_get_all_recipes_applies_cuisine_filter(self, mock_get_collection):
        mock_collection = MagicMock()
        mock_collection.find.return_value = _AsyncCursorStub([])
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_all_recipes
        await get_all_recipes(cuisine="Italian")

        called_filter = mock_collection.find.call_args[0][0]
        assert called_filter["cuisine"] == {"$regex": "Italian", "$options": "i"}

    @patch('src.routers.recipes.get_collection')
    async def test_get_all_recipes_applies_min_rating_filter(self, mock_get_collection):
        mock_collection = MagicMock()
        mock_collection.find.return_value = _AsyncCursorStub([])
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_all_recipes
        await get_all_recipes(min_rating=4.0)

        called_filter = mock_collection.find.call_args[0][0]
        assert called_filter["averageRating"] == {"$gte": 4.0}

    @patch('src.routers.recipes.get_collection')
    async def test_get_all_recipes_database_error(self, mock_get_collection):
        mock_collection = MagicMock()
        mock_collection.find.side_effect = Exception("boom")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_all_recipes
        response = await get_all_recipes()

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "DATABASE_ERROR"


from src.models.models import CreateRecipeRequest


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateRecipe:
    """Tests for POST /api/recipes/ endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_create_recipe_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.acknowledged = True
        mock_result.inserted_id = ObjectId(TEST_RECIPE_ID)
        mock_collection.insert_one.return_value = mock_result
        mock_collection.find_one.return_value = {"_id": ObjectId(TEST_RECIPE_ID), "title": "New Recipe"}
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import create_recipe
        result = await create_recipe(CreateRecipeRequest(title="New Recipe"))

        assert result.success is True
        assert result.data["title"] == "New Recipe"
        mock_collection.insert_one.assert_called_once()

    @patch('src.routers.recipes.get_collection')
    async def test_create_recipe_database_error(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.insert_one.side_effect = Exception("Insert failed")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import create_recipe
        response = await create_recipe(CreateRecipeRequest(title="New Recipe"))

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "DATABASE_ERROR"


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateRecipesBatch:
    """Tests for POST /api/recipes/batch endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_create_recipes_batch_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.inserted_ids = [ObjectId(TEST_RECIPE_ID), ObjectId("507f1f77bcf86cd799439012")]
        mock_collection.insert_many.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import create_recipes_batch
        result = await create_recipes_batch([
            CreateRecipeRequest(title="Recipe A"),
            CreateRecipeRequest(title="Recipe B"),
        ])

        assert result.success is True
        assert result.data["insertedCount"] == 2

    async def test_create_recipes_batch_empty_list(self):
        from src.routers.recipes import create_recipes_batch
        response = await create_recipes_batch([])

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "EMPTY_REQUEST"
