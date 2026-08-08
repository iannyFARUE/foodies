"""Unit tests for turning skip/limit/total into page/limit/total/pages metadata."""

import pytest
from src.utils.pagination import build_pagination


@pytest.mark.unit
class TestBuildPagination:
    def test_first_page(self):
        pagination = build_pagination(skip=0, limit=20, total=45)

        assert pagination.page == 1
        assert pagination.limit == 20
        assert pagination.total == 45

    def test_computes_page_from_skip_and_limit(self):
        pagination = build_pagination(skip=40, limit=20, total=45)

        assert pagination.page == 3

    def test_rounds_up_total_pages(self):
        pagination = build_pagination(skip=0, limit=20, total=45)

        assert pagination.pages == 3

    def test_zero_total_has_zero_pages(self):
        pagination = build_pagination(skip=0, limit=20, total=0)

        assert pagination.pages == 0
