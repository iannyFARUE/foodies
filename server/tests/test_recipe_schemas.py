"""
Unit tests for recipe and review Pydantic models.

These verify request validation only — no database or HTTP dependencies.
"""

import pytest
from pydantic import ValidationError
from src.models.models import CreateRecipeRequest, UpdateRecipeRequest, CreateReviewRequest


@pytest.mark.unit
class TestRecipeCreateValidation:
    """Tests for CreateRecipeRequest model validation."""

    def test_create_recipe_with_valid_data(self):
        recipe_data = {
            "title": "Test Recipe",
            "cuisine": "Italian",
            "difficulty": "easy",
            "ingredients": ["flour", "eggs"],
            "prepTimeMinutes": 15
        }
        recipe = CreateRecipeRequest(**recipe_data)
        assert recipe.title == "Test Recipe"
        assert recipe.cuisine == "Italian"
        assert recipe.prepTimeMinutes == 15

    def test_create_recipe_missing_required_field(self):
        recipe_data = {"cuisine": "Italian", "description": "A recipe without a title"}
        with pytest.raises(ValidationError) as exc_info:
            CreateRecipeRequest(**recipe_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("title",) for error in errors)

    def test_create_recipe_invalid_prep_time_type(self):
        recipe_data = {"title": "Test Recipe", "prepTimeMinutes": "not-a-number"}
        with pytest.raises(ValidationError) as exc_info:
            CreateRecipeRequest(**recipe_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("prepTimeMinutes",) for error in errors)

    def test_create_recipe_with_only_required_fields(self):
        recipe = CreateRecipeRequest(**{"title": "Minimal Recipe"})
        assert recipe.title == "Minimal Recipe"
        assert recipe.cuisine is None
        assert recipe.ingredients is None


@pytest.mark.unit
class TestRecipeUpdateValidation:
    """Tests for UpdateRecipeRequest model validation."""

    def test_update_recipe_with_valid_data(self):
        recipe_update = UpdateRecipeRequest(**{"title": "Updated Title", "difficulty": "hard"})
        assert recipe_update.title == "Updated Title"
        assert recipe_update.difficulty == "hard"

    def test_update_recipe_with_partial_data(self):
        recipe_update = UpdateRecipeRequest(**{"title": "Only Title Updated"})
        assert recipe_update.title == "Only Title Updated"
        assert recipe_update.cuisine is None

    def test_update_recipe_empty_data(self):
        recipe_update = UpdateRecipeRequest(**{})
        assert recipe_update.title is None
        assert recipe_update.difficulty is None


@pytest.mark.unit
class TestRecipeDataStructure:
    """Tests for recipe data structure and types."""

    def test_recipe_with_all_fields(self):
        recipe_data = {
            "title": "Complete Recipe",
            "description": "Short summary",
            "instructions": "Step 1. Step 2.",
            "cuisine": "Mexican",
            "difficulty": "medium",
            "prepTimeMinutes": 20,
            "cookTimeMinutes": 30,
            "servings": 4,
            "ingredients": ["tortilla", "beans", "cheese"],
            "tags": ["vegetarian", "quick"]
        }
        recipe = CreateRecipeRequest(**recipe_data)
        assert recipe.title == "Complete Recipe"
        assert len(recipe.ingredients) == 3
        assert len(recipe.tags) == 2

    def test_recipe_ingredients_as_list(self):
        recipe = CreateRecipeRequest(**{"title": "Ingredient Test", "ingredients": ["salt", "pepper"]})
        assert isinstance(recipe.ingredients, list)
        assert "salt" in recipe.ingredients

    def test_recipe_with_numeric_fields(self):
        recipe_data = {"title": "Numeric Test", "prepTimeMinutes": 10, "cookTimeMinutes": 25, "servings": 2}
        recipe = CreateRecipeRequest(**recipe_data)
        assert isinstance(recipe.prepTimeMinutes, int)
        assert isinstance(recipe.servings, int)


@pytest.mark.unit
class TestReviewCreateValidation:
    """Tests for CreateReviewRequest model validation."""

    def test_create_review_with_valid_data(self):
        review = CreateReviewRequest(**{"reviewerName": "Alex", "rating": 5, "comment": "Delicious!"})
        assert review.reviewerName == "Alex"
        assert review.rating == 5

    def test_create_review_missing_reviewer_name(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateReviewRequest(**{"rating": 4})
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("reviewerName",) for error in errors)

    def test_create_review_rating_above_maximum(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateReviewRequest(**{"reviewerName": "Alex", "rating": 6})
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("rating",) for error in errors)

    def test_create_review_rating_below_minimum(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateReviewRequest(**{"reviewerName": "Alex", "rating": 0})
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("rating",) for error in errors)
