"""Unit tests for the success/error response envelope helpers."""

import pytest
from src.utils.successResponse import create_success_response
from src.utils.errorResponse import create_error_response
from src.models.models import Pagination


@pytest.mark.unit
class TestCreateSuccessResponse:
    def test_wraps_data_with_default_message(self):
        response = create_success_response({"title": "Pasta"})
        assert response.success is True
        assert response.data == {"title": "Pasta"}
        assert response.message == "Operation completed successfully."
        assert response.timestamp.endswith("Z")

    def test_wraps_data_with_custom_message(self):
        response = create_success_response(["a", "b"], "Found 2 items")
        assert response.message == "Found 2 items"
        assert response.data == ["a", "b"]

    def test_wraps_data_with_pagination_metadata(self):
        pagination = Pagination(page=1, limit=20, total=45, pages=3)
        response = create_success_response(["a", "b"], pagination=pagination)
        assert response.pagination == pagination

    def test_pagination_defaults_to_none(self):
        response = create_success_response(["a", "b"])
        assert response.pagination is None


@pytest.mark.unit
class TestCreateErrorResponse:
    def test_includes_code_and_message(self):
        body = create_error_response("Not found", code="RECIPE_NOT_FOUND")
        assert body["success"] is False
        assert body["message"] == "Not found"
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"
        assert body["error"]["details"] is None

    def test_includes_details_when_provided(self):
        body = create_error_response("Bad input", code="VALIDATION_ERROR", details="field 'title' required")
        assert body["error"]["details"] == "field 'title' required"
