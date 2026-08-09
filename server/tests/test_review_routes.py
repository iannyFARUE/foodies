"""
Unit tests for review management: listing, updating, and deleting a single
review, plus the shared rating-recompute helper they all rely on.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi.responses import JSONResponse

TEST_RECIPE_ID = "507f1f77bcf86cd799439011"
TEST_REVIEW_ID = "507f1f77bcf86cd799439099"
INVALID_ID = "invalid-id"


def _mock_collections(recipe=None, stats=None):
    mock_recipes = AsyncMock()
    mock_recipes.find_one.return_value = recipe

    mock_reviews = AsyncMock()

    mock_cursor = AsyncMock()
    mock_cursor.to_list.return_value = stats if stats is not None else []
    mock_reviews.aggregate.return_value = mock_cursor

    def side_effect(name):
        return mock_recipes if name == "recipes" else mock_reviews

    return mock_recipes, mock_reviews, side_effect


@pytest.mark.unit
@pytest.mark.asyncio
class TestRecomputeRecipeRatingStats:
    @patch('src.routers.recipes.get_collection')
    async def test_sets_average_and_count_when_reviews_exist(self, mock_get_collection):
        mock_recipes, mock_reviews, side_effect = _mock_collections(
            stats=[{"averageRating": 4.5, "reviewCount": 2}]
        )
        mock_get_collection.side_effect = side_effect

        from src.routers.recipes import recompute_recipe_rating_stats
        await recompute_recipe_rating_stats(ObjectId(TEST_RECIPE_ID))

        mock_recipes.update_one.assert_called_once_with(
            {"_id": ObjectId(TEST_RECIPE_ID)},
            {"$set": {"averageRating": 4.5, "reviewCount": 2}}
        )

    @patch('src.routers.recipes.get_collection')
    async def test_resets_to_none_and_zero_when_no_reviews_remain(self, mock_get_collection):
        mock_recipes, mock_reviews, side_effect = _mock_collections(stats=[])
        mock_get_collection.side_effect = side_effect

        from src.routers.recipes import recompute_recipe_rating_stats
        await recompute_recipe_rating_stats(ObjectId(TEST_RECIPE_ID))

        mock_recipes.update_one.assert_called_once_with(
            {"_id": ObjectId(TEST_RECIPE_ID)},
            {"$set": {"averageRating": None, "reviewCount": 0}}
        )


class _AsyncCursorStub:
    """Minimal fake for a pymongo cursor: sync chain calls, async iteration."""

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
class TestGetRecipeReviews:
    """Tests for GET /api/recipes/{id}/reviews endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_returns_paginated_reviews(self, mock_get_collection):
        recipe = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Test Recipe"}
        reviews = [
            {"_id": ObjectId(TEST_REVIEW_ID), "recipe_id": ObjectId(TEST_RECIPE_ID), "reviewerName": "Alex", "rating": 5},
        ]
        mock_recipes = AsyncMock()
        mock_recipes.find_one.return_value = recipe
        mock_reviews = MagicMock()
        mock_reviews.find.return_value = _AsyncCursorStub(reviews)
        mock_reviews.count_documents = AsyncMock(return_value=1)

        def side_effect(name):
            return mock_recipes if name == "recipes" else mock_reviews
        mock_get_collection.side_effect = side_effect

        from src.routers.recipes import get_recipe_reviews
        result = await get_recipe_reviews(TEST_RECIPE_ID, limit=20, skip=0)

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0]["_id"] == TEST_REVIEW_ID
        assert result.data[0]["recipe_id"] == TEST_RECIPE_ID
        assert result.pagination.total == 1

    @patch('src.routers.recipes.get_collection')
    async def test_recipe_not_found(self, mock_get_collection):
        mock_recipes = AsyncMock()
        mock_recipes.find_one.return_value = None
        mock_get_collection.side_effect = lambda name: mock_recipes

        from src.routers.recipes import get_recipe_reviews
        response = await get_recipe_reviews(TEST_RECIPE_ID, limit=20, skip=0)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_invalid_recipe_id(self):
        from src.routers.recipes import get_recipe_reviews
        response = await get_recipe_reviews(INVALID_ID, limit=20, skip=0)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeleteReview:
    """Tests for DELETE /api/recipes/{id}/reviews/{review_id} endpoint."""

    @patch('src.routers.recipes.recompute_recipe_rating_stats')
    @patch('src.routers.recipes.get_collection')
    async def test_delete_review_success(self, mock_get_collection, mock_recompute):
        mock_reviews = AsyncMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_reviews.delete_one.return_value = mock_result
        mock_get_collection.return_value = mock_reviews
        mock_recompute.return_value = None

        from src.routers.recipes import delete_review
        result = await delete_review(TEST_RECIPE_ID, TEST_REVIEW_ID)

        assert result.success is True
        assert result.data["deletedCount"] == 1
        mock_reviews.delete_one.assert_called_once_with(
            {"_id": ObjectId(TEST_REVIEW_ID), "recipe_id": ObjectId(TEST_RECIPE_ID)}
        )
        mock_recompute.assert_called_once_with(ObjectId(TEST_RECIPE_ID))

    @patch('src.routers.recipes.recompute_recipe_rating_stats')
    @patch('src.routers.recipes.get_collection')
    async def test_delete_review_not_found(self, mock_get_collection, mock_recompute):
        mock_reviews = AsyncMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        mock_reviews.delete_one.return_value = mock_result
        mock_get_collection.return_value = mock_reviews

        from src.routers.recipes import delete_review
        response = await delete_review(TEST_RECIPE_ID, TEST_REVIEW_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "REVIEW_NOT_FOUND"
        mock_recompute.assert_not_called()

    async def test_delete_review_invalid_ids(self):
        from src.routers.recipes import delete_review
        response = await delete_review(TEST_RECIPE_ID, INVALID_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateReview:
    """Tests for PATCH /api/recipes/{id}/reviews/{review_id} endpoint."""

    @patch('src.routers.recipes.recompute_recipe_rating_stats')
    @patch('src.routers.recipes.get_collection')
    async def test_update_review_rating_recomputes_stats(self, mock_get_collection, mock_recompute):
        from src.models.models import UpdateReviewRequest
        mock_reviews = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_reviews.update_one.return_value = mock_result
        mock_reviews.find_one.return_value = {
            "_id": ObjectId(TEST_REVIEW_ID), "recipe_id": ObjectId(TEST_RECIPE_ID),
            "reviewerName": "Alex", "rating": 4, "comment": "Updated"
        }
        mock_get_collection.return_value = mock_reviews
        mock_recompute.return_value = None

        from src.routers.recipes import update_review
        result = await update_review(UpdateReviewRequest(rating=4, comment="Updated"), TEST_RECIPE_ID, TEST_REVIEW_ID)

        assert result.success is True
        assert result.data["rating"] == 4
        mock_reviews.update_one.assert_called_once_with(
            {"_id": ObjectId(TEST_REVIEW_ID), "recipe_id": ObjectId(TEST_RECIPE_ID)},
            {"$set": {"rating": 4, "comment": "Updated"}}
        )
        mock_recompute.assert_called_once_with(ObjectId(TEST_RECIPE_ID))

    @patch('src.routers.recipes.recompute_recipe_rating_stats')
    @patch('src.routers.recipes.get_collection')
    async def test_update_review_comment_only_does_not_recompute_stats(self, mock_get_collection, mock_recompute):
        from src.models.models import UpdateReviewRequest
        mock_reviews = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_reviews.update_one.return_value = mock_result
        mock_reviews.find_one.return_value = {
            "_id": ObjectId(TEST_REVIEW_ID), "recipe_id": ObjectId(TEST_RECIPE_ID),
            "reviewerName": "Alex", "rating": 5, "comment": "Just a typo fix"
        }
        mock_get_collection.return_value = mock_reviews

        from src.routers.recipes import update_review
        await update_review(UpdateReviewRequest(comment="Just a typo fix"), TEST_RECIPE_ID, TEST_REVIEW_ID)

        mock_recompute.assert_not_called()

    async def test_update_review_no_fields_provided(self):
        from src.models.models import UpdateReviewRequest
        from src.routers.recipes import update_review
        response = await update_review(UpdateReviewRequest(), TEST_RECIPE_ID, TEST_REVIEW_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "NO_UPDATE_DATA"

    @patch('src.routers.recipes.get_collection')
    async def test_update_review_not_found(self, mock_get_collection):
        from src.models.models import UpdateReviewRequest
        mock_reviews = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_reviews.update_one.return_value = mock_result
        mock_get_collection.return_value = mock_reviews

        from src.routers.recipes import update_review
        response = await update_review(UpdateReviewRequest(rating=3), TEST_RECIPE_ID, TEST_REVIEW_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "REVIEW_NOT_FOUND"

    async def test_update_review_invalid_ids(self):
        from src.models.models import UpdateReviewRequest
        from src.routers.recipes import update_review
        response = await update_review(UpdateReviewRequest(rating=3), TEST_RECIPE_ID, INVALID_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"
