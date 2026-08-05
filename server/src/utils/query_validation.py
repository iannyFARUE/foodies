"""
Allowlist validators for client-supplied MongoDB filter/update documents.

The batch update/delete endpoints let clients pass raw filter and update
objects straight through to update_many/delete_many. Without validation, a
client could use operators like $where/$expr (arbitrary JS/aggregation
evaluation) or reach fields outside the recipe schema. These validators
restrict field names to a caller-supplied allowlist and, for filters,
restrict operators to a small safe comparison set.
"""

from typing import Optional

FILTER_ALLOWED_OPERATORS = {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}


def validate_recipe_filter(filter_data: dict, allowed_fields: set) -> Optional[str]:
    """Return an error message if filter_data isn't safe/allowed, else None."""
    if not isinstance(filter_data, dict):
        return "Filter must be an object."

    for field, condition in filter_data.items():
        if not isinstance(field, str) or field not in allowed_fields:
            return f"Filter field '{field}' is not allowed."
        if isinstance(condition, dict):
            for operator in condition:
                if operator not in FILTER_ALLOWED_OPERATORS:
                    return f"Filter operator '{operator}' is not allowed on field '{field}'."
    return None


def validate_recipe_update(update_data: dict, allowed_fields: set) -> Optional[str]:
    """Return an error message if update_data isn't safe/allowed, else None."""
    if not isinstance(update_data, dict):
        return "Update must be an object."

    for field, value in update_data.items():
        if not isinstance(field, str) or "." in field or field not in allowed_fields:
            return f"Update field '{field}' is not allowed."
        if isinstance(value, dict):
            return f"Update field '{field}' may not contain a nested object."
    return None
