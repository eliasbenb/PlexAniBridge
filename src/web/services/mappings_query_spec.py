"""Shared query field specifications for mappings search."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.core.anilist import AniListClient
from src.models.db.animap import AniMap
from src.models.schemas.anilist import MediaFormat, MediaStatus

__all__ = [
    "QueryFieldKind",
    "QueryFieldOperator",
    "QueryFieldSpec",
    "QueryFieldType",
    "get_query_field_map",
    "get_query_field_specs",
]


class QueryFieldType(StrEnum):
    """Supported value shapes for booru-like query fields."""

    INT = "int"
    STRING = "string"
    ENUM = "enum"


class QueryFieldOperator(StrEnum):
    """Supported operator tokens for query fields."""

    EQ = "="
    IN = "in"
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    STAR_WILDCARD = "*"
    QMARK_WILDCARD = "?"
    RANGE = "range"


class QueryFieldKind(StrEnum):
    """Categorisation for query field resolution backends."""

    DB_SCALAR = "db_scalar"
    DB_JSON_ARRAY = "db_json_array"
    DB_JSON_DICT = "db_json_dict"
    DB_HAS = "db_has"
    ANILIST_STRING = "anilist_string"
    ANILIST_NUMERIC = "anilist_numeric"
    ANILIST_ENUM = "anilist_enum"


@dataclass(frozen=True)
class QueryFieldSpec:
    """Describes a single query-capable field."""

    key: str
    kind: QueryFieldKind
    type: QueryFieldType
    operators: Iterable[QueryFieldOperator]
    desc: str | None = None
    aliases: Iterable[str] = ()
    values: Iterable[str] | None = None
    column: Any | None = None
    json_array_numeric: bool = False
    anilist_field: str | None = None
    anilist_value_type: str | None = None
    anilist_multi_field: str | None = None


_HAS_VALUES = (
    "anilist",
    "id",
    "anidb",
    "imdb",
    "mal",
    "tmdb_movie",
    "tmdb_show",
    "tvdb",
    "tmdb_mappings",
    "tvdb_mappings",
)


_ENUM_OPS = (
    QueryFieldOperator.EQ,
    QueryFieldOperator.IN,
)
_INT_OPS = (
    QueryFieldOperator.EQ,
    QueryFieldOperator.GT,
    QueryFieldOperator.GTE,
    QueryFieldOperator.LT,
    QueryFieldOperator.LTE,
    QueryFieldOperator.RANGE,
)
_STRING_OPS = (
    QueryFieldOperator.EQ,
    QueryFieldOperator.STAR_WILDCARD,
    QueryFieldOperator.QMARK_WILDCARD,
)

_INT_IN_OPS = (*_INT_OPS, QueryFieldOperator.IN)
_STRING_IN_OPS = (*_STRING_OPS, QueryFieldOperator.IN)

_DB_FIELDS: tuple[QueryFieldSpec, ...] = (
    QueryFieldSpec(
        key="anilist",
        aliases=("id",),
        desc="AniList ID",
        kind=QueryFieldKind.DB_SCALAR,
        type=QueryFieldType.INT,
        operators=_INT_IN_OPS,
        column=AniMap.anilist_id,
    ),
    QueryFieldSpec(
        key="anidb",
        desc="AniDB ID",
        kind=QueryFieldKind.DB_SCALAR,
        type=QueryFieldType.INT,
        operators=_INT_IN_OPS,
        column=AniMap.anidb_id,
    ),
    QueryFieldSpec(
        key="imdb",
        desc="IMDb ID",
        kind=QueryFieldKind.DB_JSON_ARRAY,
        type=QueryFieldType.STRING,
        operators=_STRING_IN_OPS,
        column=AniMap.imdb_id,
        json_array_numeric=False,
    ),
    QueryFieldSpec(
        key="mal",
        desc="MyAnimeList ID",
        kind=QueryFieldKind.DB_JSON_ARRAY,
        type=QueryFieldType.INT,
        operators=_INT_IN_OPS,
        column=AniMap.mal_id,
        json_array_numeric=True,
    ),
    QueryFieldSpec(
        key="tmdb_movie",
        desc="TMDB Movie ID",
        kind=QueryFieldKind.DB_JSON_ARRAY,
        type=QueryFieldType.INT,
        operators=_INT_IN_OPS,
        column=AniMap.tmdb_movie_id,
        json_array_numeric=True,
    ),
    QueryFieldSpec(
        key="tmdb_show",
        desc="TMDB TV Show ID",
        kind=QueryFieldKind.DB_SCALAR,
        type=QueryFieldType.INT,
        operators=_INT_IN_OPS,
        column=AniMap.tmdb_show_id,
    ),
    QueryFieldSpec(
        key="tvdb",
        desc="TVDB ID",
        kind=QueryFieldKind.DB_SCALAR,
        type=QueryFieldType.INT,
        operators=_INT_IN_OPS,
        column=AniMap.tvdb_id,
    ),
    QueryFieldSpec(
        key="tmdb_mappings",
        desc="Season/episode mappings",
        kind=QueryFieldKind.DB_JSON_DICT,
        type=QueryFieldType.STRING,
        operators=_STRING_IN_OPS,
        column=AniMap.tmdb_mappings,
    ),
    QueryFieldSpec(
        key="tvdb_mappings",
        desc="Season/episode mappings",
        kind=QueryFieldKind.DB_JSON_DICT,
        type=QueryFieldType.STRING,
        operators=_STRING_IN_OPS,
        column=AniMap.tvdb_mappings,
    ),
    QueryFieldSpec(
        key="has",
        desc="Presence filter",
        kind=QueryFieldKind.DB_HAS,
        type=QueryFieldType.ENUM,
        operators=_ENUM_OPS,
        values=_HAS_VALUES,
    ),
)
try:
    _anilist_client = AniListClient(anilist_token=None)
    _anilist_genres = _anilist_client.available_genres
    _anilist_tags = _anilist_client.available_tags
except Exception:  # This is an import-time operation; can't afford to fail
    _anilist_genres = []
    _anilist_tags = []

_ANILIST_FIELDS: tuple[QueryFieldSpec, ...] = (
    QueryFieldSpec(
        key="anilist.title",
        desc="AniList title search",
        kind=QueryFieldKind.ANILIST_STRING,
        type=QueryFieldType.STRING,
        operators=(QueryFieldOperator.EQ,),
        anilist_field="search",
        anilist_value_type="string",
    ),
    QueryFieldSpec(
        key="anilist.duration",
        desc="Episode duration (minutes)",
        kind=QueryFieldKind.ANILIST_NUMERIC,
        type=QueryFieldType.INT,
        operators=_INT_OPS,
        anilist_field="duration",
        anilist_value_type="int",
    ),
    QueryFieldSpec(
        key="anilist.episodes",
        desc="Episode count",
        kind=QueryFieldKind.ANILIST_NUMERIC,
        type=QueryFieldType.INT,
        operators=_INT_OPS,
        anilist_field="episodes",
        anilist_value_type="int",
    ),
    QueryFieldSpec(
        key="anilist.start_date",
        desc="Start date (YYYYMMDD)",
        kind=QueryFieldKind.ANILIST_NUMERIC,
        type=QueryFieldType.INT,
        operators=_INT_OPS,
        anilist_field="startDate",
        anilist_value_type="fuzzy_date",
    ),
    QueryFieldSpec(
        key="anilist.end_date",
        desc="End date (YYYYMMDD)",
        kind=QueryFieldKind.ANILIST_NUMERIC,
        type=QueryFieldType.INT,
        operators=_INT_OPS,
        anilist_field="endDate",
        anilist_value_type="fuzzy_date",
    ),
    QueryFieldSpec(
        key="anilist.format",
        desc="AniList format",
        kind=QueryFieldKind.ANILIST_ENUM,
        type=QueryFieldType.ENUM,
        operators=_ENUM_OPS,
        values=tuple(
            m.value for m in MediaFormat if m not in {"MANGA", "NOVEL", "ONE_SHOT"}
        ),
        anilist_field="format",
        anilist_value_type="enum",
        anilist_multi_field="format_in",
    ),
    QueryFieldSpec(
        key="anilist.status",
        desc="AniList status",
        kind=QueryFieldKind.ANILIST_ENUM,
        type=QueryFieldType.ENUM,
        operators=_ENUM_OPS,
        values=tuple(s.value for s in MediaStatus if s not in {MediaStatus.HIATUS}),
        anilist_field="status",
        anilist_value_type="enum",
        anilist_multi_field="status_in",
    ),
    # Annoyingly, AniList genres and tags diverge from typical `_in` behavior;
    # instead of matching any of the provided values, they match ALL provided values.
    # Essentially, they behave like a series of ANDed equality checks.
    # Multivalue searches for these fields will be disabled to avoid confusion.
    QueryFieldSpec(
        key="anilist.genre",
        desc="AniList genre",
        kind=QueryFieldKind.ANILIST_ENUM,
        type=QueryFieldType.ENUM,
        operators=(QueryFieldOperator.EQ,),
        values=_anilist_genres,
        anilist_field="genre",
        anilist_value_type="enum",
    ),
    QueryFieldSpec(
        key="anilist.tag",
        desc="AniList tag",
        kind=QueryFieldKind.ANILIST_ENUM,
        type=QueryFieldType.ENUM,
        operators=(QueryFieldOperator.EQ,),
        values=_anilist_tags,
        anilist_field="tag",
        anilist_value_type="enum",
    ),
    QueryFieldSpec(
        key="anilist.average_score",
        desc="Average AniList score (0-100)",
        kind=QueryFieldKind.ANILIST_NUMERIC,
        type=QueryFieldType.INT,
        operators=_INT_OPS,
        anilist_field="averageScore",
        anilist_value_type="int",
    ),
    QueryFieldSpec(
        key="anilist.popularity",
        desc="AniList popularity",
        kind=QueryFieldKind.ANILIST_NUMERIC,
        type=QueryFieldType.INT,
        operators=_INT_OPS,
        anilist_field="popularity",
        anilist_value_type="int",
    ),
)


_QUERY_FIELDS: tuple[QueryFieldSpec, ...] = _DB_FIELDS + _ANILIST_FIELDS
_FIELD_MAP: dict[str, QueryFieldSpec] = {}
for spec in _QUERY_FIELDS:
    _FIELD_MAP[spec.key.lower()] = spec
    for alias in spec.aliases:
        _FIELD_MAP[alias.lower()] = spec


def get_query_field_specs() -> tuple[QueryFieldSpec, ...]:
    """Return the immutable collection of query field specifications.

    Returns:
        tuple[QueryFieldSpec, ...]: Collection of query field specifications.
    """
    return _QUERY_FIELDS


def get_query_field_map() -> Mapping[str, QueryFieldSpec]:
    """Return a mapping of lowercase key/aliases to field specs.

    Returns:
        Mapping[str, QueryFieldSpec]: Mapping of lowercase key/aliases to field specs.
    """
    return _FIELD_MAP
