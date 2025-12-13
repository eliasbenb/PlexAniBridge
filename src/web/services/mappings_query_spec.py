"""Query field specifications for mapping graph search."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.models.db.animap import AnimapEntry

__all__ = [
    "QueryFieldKind",
    "QueryFieldOperator",
    "QueryFieldSpec",
    "QueryFieldType",
    "get_query_field_map",
    "get_query_field_specs",
]


class QueryFieldType(StrEnum):
    """Supported value shapes for query fields."""

    STRING = "string"


class QueryFieldOperator(StrEnum):
    """Supported operators for mapping queries."""

    EQ = "="
    LIKE = "like"


class QueryFieldKind(StrEnum):
    """Categories for query backends."""

    DB_SCALAR = "db_scalar"


@dataclass(frozen=True)
class QueryFieldSpec:
    """Specification describing a single searchable field."""

    key: str
    kind: QueryFieldKind
    type: QueryFieldType
    operators: Iterable[QueryFieldOperator]
    desc: str | None = None
    aliases: Iterable[str] = ()
    values: Iterable[str] | None = None
    column: Any | None = None


_DB_FIELDS: tuple[QueryFieldSpec, ...] = (
    QueryFieldSpec(
        key="provider",
        desc="Source provider",
        kind=QueryFieldKind.DB_SCALAR,
        type=QueryFieldType.STRING,
        operators=(QueryFieldOperator.EQ,),
        column=AnimapEntry.provider,
    ),
    QueryFieldSpec(
        key="entry_id",
        desc="Entry identifier",
        kind=QueryFieldKind.DB_SCALAR,
        type=QueryFieldType.STRING,
        operators=(QueryFieldOperator.EQ, QueryFieldOperator.LIKE),
        column=AnimapEntry.entry_id,
    ),
    QueryFieldSpec(
        key="scope",
        desc="Entry scope (movie/s#)",
        kind=QueryFieldKind.DB_SCALAR,
        type=QueryFieldType.STRING,
        operators=(QueryFieldOperator.EQ,),
        column=AnimapEntry.entry_scope,
    ),
)


def get_query_field_specs() -> tuple[QueryFieldSpec, ...]:
    """Return all supported query field specs."""
    return _DB_FIELDS


def get_query_field_map() -> Mapping[str, QueryFieldSpec]:
    """Return a map of field key to spec."""
    return {spec.key: spec for spec in _DB_FIELDS}
