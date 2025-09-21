"""Reusable SQL utility functions."""

from typing import Any

from sqlalchemy.orm.base import Mapped
from sqlalchemy.sql import and_, cast, column, exists, false, func, select
from sqlalchemy.sql.elements import BinaryExpression, ColumnElement, UnaryExpression
from sqlalchemy.sql.sqltypes import Integer

__all__ = [
    "json_array_between",
    "json_array_compare",
    "json_array_contains",
    "json_dict_has_key",
    "json_dict_has_value",
]


def json_array_contains(field: Mapped, values: list[Any]) -> ColumnElement[bool]:
    """Generates a JSON_CONTAINS function for the given field.

    Creates SQL conditions to check if any of the provided values exist
    within a JSON array field using SQLite's json_each function.

    Args:
        field (Mapped): SQLAlchemy mapped field representing a JSON array column
        values (list[Any]): List of values to search for within the JSON array

    Returns:
        ColumnElement[bool]: SQL condition that evaluates to True if any value
                                is found
    """
    if not values:
        return false()

    return exists(
        select(1).select_from(func.json_each(field)).where(column("value").in_(values))
    )


def json_dict_has_key(field: Mapped, key: str) -> BinaryExpression:
    """Generate a SQL expression for checking if a JSON field contains a key.

    Uses SQLite's json_type function to check if a specific key exists
    in a JSON object field.

    Args:
        field (Mapped): SQLAlchemy mapped field representing a JSON column
        key (str): JSON object key to search for (e.g., "s1" for season 1)

    Returns:
        BinaryExpression: SQL condition that evaluates to True if key exists
    """
    return func.json_type(field, f"$.{key}").is_not(None)


def json_dict_has_value(field: Mapped, value: Any) -> UnaryExpression:
    """Generate a SQL expression for checking if a JSON field contains a value.

    Uses SQLite's json_each function to check if a specific value exists
    in a JSON object field.

    Args:
        field (Mapped): SQLAlchemy mapped field representing a JSON column
        value (Any): Value to search for within the JSON object

    Returns:
        UnaryExpression: SQL condition that evaluates to True if value exists
    """
    return exists(
        select(1).select_from(func.json_each(field)).where(column("value") == value)
    )


def json_array_between(col, lo: int, hi: int):
    """Check if any element of a JSON numeric array is within [lo, hi]."""
    v = cast(column("value"), Integer)
    return exists(
        select(1).select_from(func.json_each(col)).where(and_(v >= lo, v <= hi))
    )


def json_array_compare(col, op: str, num: int) -> ColumnElement[bool]:
    """Compare any element of a JSON numeric array to a number.

    Supported operators: ">", ">=", "<", "<=".
    """
    v = cast(column("value"), Integer)
    if op == ">":
        comp = v > num
    elif op == ">=":
        comp = v >= num
    elif op == "<":
        comp = v < num
    elif op == "<=":
        comp = v <= num
    else:
        # Fallback to false for unsupported operators
        return false()
    return exists(select(1).select_from(func.json_each(col)).where(comp))
