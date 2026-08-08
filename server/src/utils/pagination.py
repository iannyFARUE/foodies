"""Turns skip/limit/total into page/limit/total/pages metadata for list responses."""

import math

from src.models.models import Pagination


def build_pagination(skip: int, limit: int, total: int) -> Pagination:
    return Pagination(
        page=(skip // limit) + 1 if limit else 1,
        limit=limit,
        total=total,
        pages=math.ceil(total / limit) if limit else 0,
    )
