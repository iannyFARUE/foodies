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


from src.models.models import UpdateRecipeRequest


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateRecipe:
    """Tests for PATCH /api/recipes/{id} endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_update_recipe_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result
        mock_collection.find_one.return_value = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Updated"}
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import update_recipe
        result = await update_recipe(UpdateRecipeRequest(title="Updated"), recipe_id=TEST_RECIPE_ID)

        assert result.success is True
        assert result.data["title"] == "Updated"

    async def test_update_recipe_no_fields_provided(self):
        from src.routers.recipes import update_recipe
        response = await update_recipe(UpdateRecipeRequest(), recipe_id=TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "NO_UPDATE_DATA"

    @patch('src.routers.recipes.get_collection')
    async def test_update_recipe_not_found(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_collection.update_one.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import update_recipe
        response = await update_recipe(UpdateRecipeRequest(title="Updated"), recipe_id=TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_update_recipe_invalid_id(self):
        from src.routers.recipes import update_recipe
        response = await update_recipe(UpdateRecipeRequest(title="Updated"), recipe_id=INVALID_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateRecipesBatch:
    """Tests for PATCH /api/recipes/ endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_update_recipes_batch_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 3
        mock_result.modified_count = 3
        mock_collection.update_many.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import update_recipes_batch
        result = await update_recipes_batch({"filter": {"cuisine": "Italian"}, "update": {"difficulty": "easy"}})

        assert result.success is True
        assert result.data["matchedCount"] == 3
        assert result.data["modifiedCount"] == 3

    async def test_update_recipes_batch_missing_filter(self):
        from src.routers.recipes import update_recipes_batch
        response = await update_recipes_batch({"update": {"difficulty": "easy"}})

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "MISSING_FILTER"


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeleteRecipeById:
    """Tests for DELETE /api/recipes/{id} endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_delete_recipe_by_id_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_collection.delete_one.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import delete_recipe_by_id
        result = await delete_recipe_by_id(TEST_RECIPE_ID)

        assert result.success is True
        assert result.data["deletedCount"] == 1

    @patch('src.routers.recipes.get_collection')
    async def test_delete_recipe_by_id_not_found(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        mock_collection.delete_one.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import delete_recipe_by_id
        response = await delete_recipe_by_id(TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_delete_recipe_by_id_invalid_id(self):
        from src.routers.recipes import delete_recipe_by_id
        response = await delete_recipe_by_id(INVALID_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400


@pytest.mark.unit
@pytest.mark.asyncio
class TestFindAndDeleteRecipe:
    """Tests for DELETE /api/recipes/{id}/find-and-delete endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_find_and_delete_recipe_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.find_one_and_delete.return_value = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Deleted Recipe"}
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import find_and_delete_recipe
        result = await find_and_delete_recipe(TEST_RECIPE_ID)

        assert result.success is True
        assert result.data["title"] == "Deleted Recipe"

    @patch('src.routers.recipes.get_collection')
    async def test_find_and_delete_recipe_not_found(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.find_one_and_delete.return_value = None
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import find_and_delete_recipe
        response = await find_and_delete_recipe(TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeleteRecipesBatch:
    """Tests for DELETE /api/recipes/ endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_delete_recipes_batch_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 3
        mock_collection.delete_many.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import delete_recipes_batch
        result = await delete_recipes_batch({"filter": {"cuisine": "Italian"}})

        assert result.success is True
        assert result.data["deletedCount"] == 3

    async def test_delete_recipes_batch_missing_filter(self):
        from src.routers.recipes import delete_recipes_batch
        response = await delete_recipes_batch({})

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "MISSING_FILTER"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetDistinctCuisines:
    """Tests for GET /api/recipes/cuisines endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_get_distinct_cuisines_returns_sorted_list(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.distinct.return_value = ["Mexican", "Italian", None, "", "Italian"]
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_distinct_cuisines
        result = await get_distinct_cuisines()

        assert result.success is True
        assert result.data == ["Italian", "Italian", "Mexican"]

    @patch('src.routers.recipes.get_collection')
    async def test_get_distinct_cuisines_database_error(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.distinct.side_effect = Exception("boom")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_distinct_cuisines
        response = await get_distinct_cuisines()

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500


from src.models.models import CreateReviewRequest


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateReview:
    """Tests for POST /api/recipes/{id}/reviews endpoint."""

    def _mock_collections(self, recipe=None, insert_result=None, created_review=None, stats=None):
        mock_recipes = AsyncMock()
        mock_recipes.find_one.return_value = recipe

        mock_reviews = AsyncMock()
        mock_reviews.insert_one.return_value = insert_result
        mock_reviews.find_one.return_value = created_review

        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = stats or []
        mock_reviews.aggregate.return_value = mock_cursor

        def side_effect(name):
            return mock_recipes if name == "recipes" else mock_reviews

        return mock_recipes, mock_reviews, side_effect

    @patch('src.routers.recipes.get_collection')
    async def test_create_review_success(self, mock_get_collection):
        recipe = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Test Recipe"}
        insert_result = MagicMock()
        insert_result.inserted_id = ObjectId("507f1f77bcf86cd799439099")
        created_review = {
            "_id": ObjectId("507f1f77bcf86cd799439099"),
            "recipe_id": ObjectId(TEST_RECIPE_ID),
            "reviewerName": "Alex",
            "rating": 5,
            "comment": "Great!",
        }
        stats = [{"averageRating": 5.0, "reviewCount": 1}]

        mock_recipes, mock_reviews, side_effect = self._mock_collections(
            recipe=recipe, insert_result=insert_result, created_review=created_review, stats=stats
        )
        mock_get_collection.side_effect = side_effect

        from src.routers.recipes import create_review
        result = await create_review(TEST_RECIPE_ID, CreateReviewRequest(reviewerName="Alex", rating=5, comment="Great!"))

        assert result.success is True
        assert result.data["reviewerName"] == "Alex"
        mock_recipes.update_one.assert_called_once()
        update_call_kwargs = mock_recipes.update_one.call_args[0][1]
        assert update_call_kwargs["$set"]["averageRating"] == 5.0
        assert update_call_kwargs["$set"]["reviewCount"] == 1

    @patch('src.routers.recipes.get_collection')
    async def test_create_review_recipe_not_found(self, mock_get_collection):
        mock_recipes, mock_reviews, side_effect = self._mock_collections(recipe=None)
        mock_get_collection.side_effect = side_effect

        from src.routers.recipes import create_review
        response = await create_review(TEST_RECIPE_ID, CreateReviewRequest(reviewerName="Alex", rating=5))

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_create_review_invalid_recipe_id(self):
        from src.routers.recipes import create_review
        response = await create_review(INVALID_RECIPE_ID, CreateReviewRequest(reviewerName="Alex", rating=5))

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAggregateByCuisine:
    """Tests for GET /api/recipes/aggregations/byCuisine endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_aggregate_by_cuisine_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = [
            {"cuisine": "Italian", "recipeCount": 5, "averageRating": 4.2},
            {"cuisine": "Mexican", "recipeCount": 3, "averageRating": 3.8},
        ]
        mock_collection.aggregate.return_value = mock_cursor
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import aggregate_recipes_by_cuisine
        result = await aggregate_recipes_by_cuisine()

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0]["cuisine"] == "Italian"

    @patch('src.routers.recipes.get_collection')
    async def test_aggregate_by_cuisine_database_error(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.aggregate.side_effect = Exception("boom")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import aggregate_recipes_by_cuisine
        response = await aggregate_recipes_by_cuisine()

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500


@pytest.mark.unit
@pytest.mark.asyncio
class TestAggregateTopIngredients:
    """Tests for GET /api/recipes/aggregations/topIngredients endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_aggregate_top_ingredients_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = [
            {"ingredient": "salt", "recipeCount": 20},
            {"ingredient": "garlic", "recipeCount": 15},
        ]
        mock_collection.aggregate.return_value = mock_cursor
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import aggregate_top_ingredients
        result = await aggregate_top_ingredients()

        assert result.success is True
        assert result.data[0]["ingredient"] == "salt"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAggregateRecentReviews:
    """Tests for GET /api/recipes/aggregations/recentReviews endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_aggregate_recent_reviews_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = [
            {
                "_id": ObjectId(TEST_RECIPE_ID),
                "title": "Test Recipe",
                "cuisine": "Italian",
                "recentReviews": [{"reviewerName": "Alex", "rating": 5, "comment": "Great", "date": "2026-01-01"}],
                "totalReviews": 1
            }
        ]
        mock_collection.aggregate.return_value = mock_cursor
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import aggregate_recipes_recent_reviews
        # Pass recipe_id explicitly: calling the handler directly (bypassing
        # FastAPI's request handling) means unset Query(...) params keep their
        # raw Python default, which is the Query object itself, not None.
        result = await aggregate_recipes_recent_reviews(recipe_id=None)

        assert result.success is True
        assert result.data[0]["_id"] == TEST_RECIPE_ID
        assert result.data[0]["totalReviews"] == 1

    async def test_aggregate_recent_reviews_invalid_recipe_id(self):
        from src.routers.recipes import aggregate_recipes_recent_reviews
        response = await aggregate_recipes_recent_reviews(recipe_id=INVALID_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"


@pytest.mark.unit
@pytest.mark.asyncio
class TestSearchRecipes:
    """Tests for GET /api/recipes/search endpoint."""

    @patch('src.routers.recipes.execute_aggregation')
    async def test_search_recipes_success(self, mock_execute_aggregation):
        mock_execute_aggregation.return_value = [{
            "totalCount": [{"count": 1}],
            "results": [{"_id": ObjectId(TEST_RECIPE_ID), "title": "Garlic Pasta", "description": "Garlicky and rich"}]
        }]

        from src.routers.recipes import search_recipes
        # Explicit defaults: calling the handler directly bypasses FastAPI's
        # request handling, so unset Query(...) params keep the raw Query
        # object as their Python-level default rather than being resolved.
        result = await search_recipes(description="garlic", search_operator="must")

        assert result.success is True
        assert result.data.totalCount == 1
        assert result.data.recipes[0].title == "Garlic Pasta"

    async def test_search_recipes_missing_params(self):
        from src.routers.recipes import search_recipes
        response = await search_recipes(search_operator="must")

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "MISSING_SEARCH_PARAMS"

    async def test_search_recipes_invalid_operator(self):
        from src.routers.recipes import search_recipes
        response = await search_recipes(description="garlic", search_operator="invalid")

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_SEARCH_OPERATOR"

    @patch('src.routers.recipes.execute_aggregation')
    async def test_search_recipes_no_results(self, mock_execute_aggregation):
        mock_execute_aggregation.return_value = []

        from src.routers.recipes import search_recipes
        result = await search_recipes(description="nonexistent", search_operator="must")

        assert result.success is True
        assert result.data.totalCount == 0
        assert result.data.recipes == []
