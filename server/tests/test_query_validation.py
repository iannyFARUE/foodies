"""
Unit tests for the batch filter/update allowlist validators.

These guard the PATCH /api/recipes/ and DELETE /api/recipes/ batch endpoints
against NoSQL injection via client-supplied filter/update documents (e.g.
$where, $expr, or arbitrary field names).
"""

import pytest
from src.utils.query_validation import validate_recipe_filter, validate_recipe_update

ALLOWED_FIELDS = {"cuisine", "difficulty", "prepTimeMinutes"}


@pytest.mark.unit
class TestValidateRecipeFilter:
    def test_rejects_field_not_in_allowlist(self):
        error = validate_recipe_filter({"secretField": "x"}, ALLOWED_FIELDS)
        assert error is not None

    def test_allows_plain_value_on_allowed_field(self):
        error = validate_recipe_filter({"cuisine": "Italian"}, ALLOWED_FIELDS)
        assert error is None

    def test_allows_whitelisted_operator_on_allowed_field(self):
        error = validate_recipe_filter({"prepTimeMinutes": {"$lte": 30}}, ALLOWED_FIELDS)
        assert error is None

    def test_rejects_top_level_where_operator(self):
        error = validate_recipe_filter(
            {"$where": "sleep(1000) || true"}, ALLOWED_FIELDS
        )
        assert error is not None

    def test_rejects_nested_where_operator(self):
        error = validate_recipe_filter(
            {"cuisine": {"$where": "sleep(1000) || true"}}, ALLOWED_FIELDS
        )
        assert error is not None


@pytest.mark.unit
class TestValidateRecipeUpdate:
    def test_rejects_field_not_in_allowlist(self):
        error = validate_recipe_update({"averageRating": 5.0}, ALLOWED_FIELDS)
        assert error is not None

    def test_allows_plain_value_on_allowed_field(self):
        error = validate_recipe_update({"difficulty": "easy"}, ALLOWED_FIELDS)
        assert error is None

    def test_rejects_dotted_field_name(self):
        error = validate_recipe_update({"cuisine.nested": "x"}, ALLOWED_FIELDS)
        assert error is not None

    def test_rejects_nested_operator_value(self):
        error = validate_recipe_update(
            {"cuisine": {"$where": "sleep(1000) || true"}}, ALLOWED_FIELDS
        )
        assert error is not None
