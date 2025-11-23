"""Mappings service for CRUD operations, listing, and provenance updates."""

import asyncio
import calendar
import re
from collections import deque
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, ClassVar

from pyparsing import ParseResults
from sqlalchemy import and_, func, or_, select
from sqlalchemy.sql import exists

from src.config.database import db
from src.config.settings import get_config
from src.core.anilist import AniListClient
from src.exceptions import (
    AniListFilterError,
    AniListSearchError,
    BooruQueryEvaluationError,
    BooruQuerySyntaxError,
    MappingNotFoundError,
)
from src.models.db.animap import AniMap
from src.models.db.provenance import AniMapProvenance
from src.models.schemas.anilist import MediaWithoutList as AniListMetadata
from src.utils.booru_query import (
    And,
    KeyTerm,
    Node,
    Not,
    Or,
    collect_bare_terms,
    collect_key_terms,
    evaluate,
    parse_query,
)
from src.utils.sql import (
    json_array_between,
    json_array_compare,
    json_array_contains,
    json_array_exists,
    json_array_like,
    json_dict_has_key,
    json_dict_has_value,
    json_dict_key_like,
    json_dict_value_like,
)
from src.web.services.mappings_query_spec import (
    QueryFieldKind,
    QueryFieldSpec,
    get_query_field_map,
)
from src.web.state import get_app_state

__all__ = ["MappingsService", "get_mappings_service"]


class MappingsService:
    """Service to manage custom mappings and DB provenance."""

    _FIELD_MAP: ClassVar[Mapping[str, QueryFieldSpec]] = get_query_field_map()
    _ANILIST_KINDS: ClassVar[frozenset[QueryFieldKind]] = frozenset(
        {
            QueryFieldKind.ANILIST_STRING,
            QueryFieldKind.ANILIST_NUMERIC,
            QueryFieldKind.ANILIST_ENUM,
        }
    )

    # The max AniList results must be greater than the total number of media entries
    # (21K+ as of 10/2025)
    _ANILIST_MAX_RESULTS: ClassVar[int] = 25000
    _CMP_RE: ClassVar[re.Pattern[str]] = re.compile(r"^(>=|>|<=|<)(\d+)$")
    _RANGE_RE: ClassVar[re.Pattern[str]] = re.compile(r"^(\d+)\.\.(\d+)$")

    def __init__(self) -> None:
        """Initialize service with config and paths."""
        self.upstream_url: str | None = get_config().mappings_url

    @staticmethod
    def _fetch_ids(ctx, stmt) -> set[int]:
        """Executes a statement and returns AniList identifiers."""
        return {int(aid) for aid in ctx.session.execute(stmt).scalars()}

    def _parse_numeric_filters(
        self, raw: Any
    ) -> tuple[tuple[str, int] | None, tuple[int, int] | None, str]:
        """Parses comparison and range tokens from raw filter input."""
        text = "" if raw is None else str(raw)
        cmp_match = self._CMP_RE.match(text)
        range_match = self._RANGE_RE.match(text)
        cmp_filter = (
            (cmp_match.group(1), int(cmp_match.group(2))) if cmp_match else None
        )
        range_filter = (
            (int(range_match.group(1)), int(range_match.group(2)))
            if range_match
            else None
        )
        return cmp_filter, range_filter, text

    @staticmethod
    def _normalize_text_query(value: str) -> str:
        """Collapse whitespace and strip wildcard markers for AniList text search."""
        cleaned = value.replace("*", " ").replace("?", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _parse_int_value(raw_value: str) -> int | None:
        """Safely convert a string to integer if possible."""
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_fuzzy_date_int(raw_value: str) -> int | None:
        """Parse fuzzy date input (YYYYMMDD) into AniList integer format."""
        digits = "".join(ch for ch in str(raw_value) if ch.isdigit())
        if not digits:
            return None
        if len(digits) > 8:
            digits = digits[:8]
        digits = digits.ljust(8, "0")
        try:
            return int(digits)
        except ValueError:
            return None

    @staticmethod
    def _normalize_fuzzy_date_number(value: int) -> int:
        """Expand shorthand numeric values (e.g., 2016) into fuzzy date ints."""
        parsed = MappingsService._parse_fuzzy_date_int(str(value))
        return parsed if parsed is not None else value

    @staticmethod
    def _datetime_to_fuzzy(dt: datetime) -> int:
        """Convert datetime into AniList fuzzy integer representation."""
        return dt.year * 10000 + dt.month * 100 + dt.day

    def _build_anilist_term_filters(
        self,
        spec: QueryFieldSpec,
        raw_value: str,
        multi_values: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """Translate an AniList term into GraphQL filter arguments."""
        value = raw_value.strip()
        values_tuple = (
            tuple(dict.fromkeys(multi_values or ())) if multi_values else None
        )

        if not spec.anilist_field:
            raise AniListFilterError(f"AniList field mapping missing for '{spec.key}'")

        if spec.kind == QueryFieldKind.ANILIST_STRING:
            if values_tuple:
                if not spec.anilist_multi_field:
                    raise AniListFilterError(
                        f"AniList filter '{spec.key}' does not support multiple values"
                    )
                normalized = [self._normalize_text_query(item) for item in values_tuple]
                filtered = [item for item in normalized if item]
                if not filtered:
                    raise AniListFilterError(
                        f"AniList filter '{spec.key}' requires at least one value"
                    )
                unique = list(dict.fromkeys(filtered))
                return {spec.anilist_multi_field: unique}
            text = self._normalize_text_query(value)
            if not text:
                raise AniListFilterError(
                    f"AniList filter '{spec.key}' requires a non-empty value"
                )
            return {spec.anilist_field: text}

        if spec.kind == QueryFieldKind.ANILIST_ENUM:
            allowed = spec.values or ()
            if not allowed:
                raise AniListFilterError(
                    f"AniList filter '{spec.key}' is not configured with values"
                )
            lookup = {val: val for val in allowed}
            lookup.update({val.lower(): val for val in allowed})
            lookup.update({val.upper(): val for val in allowed})

            def _resolve_enum(candidate: str) -> str:
                if not candidate:
                    raise AniListFilterError(
                        f"AniList filter '{spec.key}' requires a value"
                    )
                resolved = lookup.get(candidate)
                if resolved is None:
                    resolved = lookup.get(candidate.lower())
                if resolved is None:
                    resolved = lookup.get(candidate.upper())
                if resolved is None:
                    raise AniListFilterError(
                        f"'{candidate}' is not a valid value for AniList filter "
                        f"'{spec.key}'"
                    )
                return resolved

            if values_tuple:
                if not spec.anilist_multi_field:
                    raise AniListFilterError(
                        f"AniList filter '{spec.key}' does not support multiple values"
                    )
                resolved_values = [_resolve_enum(item) for item in values_tuple]
                unique_values = list(dict.fromkeys(resolved_values))
                if not unique_values:
                    raise AniListFilterError(
                        f"AniList filter '{spec.key}' requires a value"
                    )
                return {spec.anilist_multi_field: unique_values}

            resolved = _resolve_enum(value)
            return {spec.anilist_field: resolved}

        if spec.kind == QueryFieldKind.ANILIST_NUMERIC:
            if values_tuple:
                raise AniListFilterError(
                    f"AniList filter '{spec.key}' does not support multiple values"
                )
            cmp_filter, range_filter, text_value = self._parse_numeric_filters(value)
            filters_dict = self._build_anilist_numeric_filters(
                spec, cmp_filter, range_filter, text_value
            )
            if not filters_dict:
                raise AniListFilterError(
                    f"AniList filter '{spec.key}' has an invalid numeric value"
                )
            return filters_dict

        raise AniListFilterError(f"AniList filter '{spec.key}' is not supported")

    async def _resolve_anilist_term(
        self,
        client: AniListClient,
        spec: QueryFieldSpec,
        raw_value: str,
    ) -> set[int]:
        """Resolve AniList-backed query terms into identifier sets."""
        filters = self._build_anilist_term_filters(spec, raw_value)

        try:
            ids = await client.search_media_ids(
                filters=filters, max_results=self._ANILIST_MAX_RESULTS
            )
        except (AniListFilterError, AniListSearchError):
            raise
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise AniListSearchError(
                f"Failed to resolve AniList filter '{spec.key}'"
            ) from exc
        return set(ids)

    def _collect_anilist_and_groups(self, node: Node) -> list[list[KeyTerm]]:
        """Collect AniList key term groups that share a direct AND relationship."""
        groups: list[list[KeyTerm]] = []
        assigned: set[int] = set()

        def visit(current: Any) -> None:
            if isinstance(current, And):
                direct_terms: list[KeyTerm] = []
                for child in current.children:
                    if isinstance(child, KeyTerm):
                        spec = self._FIELD_MAP.get(child.key.lower())
                        if (
                            spec
                            and spec.kind in self._ANILIST_KINDS
                            and id(child) not in assigned
                        ):
                            direct_terms.append(child)
                    else:
                        visit(child)
                if len(direct_terms) >= 2:
                    groups.append(direct_terms)
                    assigned.update(id(term) for term in direct_terms)
                return

            if isinstance(current, Or):
                for child in current.children:
                    visit(child)
                return

            if isinstance(current, Not):
                visit(current.child)
                return

            if isinstance(current, ParseResults):
                for child in current:
                    visit(child)
                return

            if isinstance(current, list):
                for child in current:
                    visit(child)

        visit(node)
        return groups

    @staticmethod
    def _fuzzy_to_datetime(value: int, bias: str) -> datetime:
        """Convert fuzzy integer into datetime, biasing toward range edge."""
        year = max(1, value // 10000)
        month = (value // 100) % 100
        day = value % 100

        if month <= 0:
            month = 1 if bias == "lower" else 12
        if day <= 0:
            day = 1 if bias == "lower" else calendar.monthrange(year, month)[1]

        return datetime(year=year, month=month, day=day)

    @classmethod
    def _fuzzy_lower_threshold(cls, value: int) -> int:
        """Inclusive lower bound helper for AniList fuzzy dates."""
        try:
            dt = cls._fuzzy_to_datetime(value, "lower") - timedelta(days=1)
        except Exception:
            return value
        return cls._datetime_to_fuzzy(dt)

    @classmethod
    def _fuzzy_upper_threshold(cls, value: int) -> int:
        """Inclusive upper bound helper for AniList fuzzy dates."""
        try:
            dt = cls._fuzzy_to_datetime(value, "upper") + timedelta(days=1)
        except Exception:
            return value
        return cls._datetime_to_fuzzy(dt)

    def _build_anilist_numeric_filters(
        self,
        spec: QueryFieldSpec,
        cmp_filter: tuple[str, int] | None,
        range_filter: tuple[int, int] | None,
        raw_value: str,
    ) -> dict[str, Any] | None:
        """Translate numeric filters into AniList GraphQL arguments."""
        field = spec.anilist_field
        if not field:
            return None

        value_type = spec.anilist_value_type or "int"
        is_fuzzy = value_type == "fuzzy_date"

        def _inclusive_lower(num: int) -> int:
            if value_type == "fuzzy_date":
                return self._fuzzy_lower_threshold(num)
            return num - 1

        def _inclusive_upper(num: int) -> int:
            if value_type == "fuzzy_date":
                return self._fuzzy_upper_threshold(num)
            return num + 1

        if range_filter:
            lo, hi = range_filter
            if lo > hi:
                lo, hi = hi, lo
            if is_fuzzy:
                lo = self._normalize_fuzzy_date_number(lo)
                hi = self._normalize_fuzzy_date_number(hi)
            return {
                f"{field}_greater": _inclusive_lower(lo),
                f"{field}_lesser": _inclusive_upper(hi),
            }

        if cmp_filter:
            op, num = cmp_filter
            if is_fuzzy:
                num = self._normalize_fuzzy_date_number(num)
            if value_type == "fuzzy_date":
                if op == ">":
                    return {f"{field}_greater": num}
                if op == ">=":
                    return {f"{field}_greater": self._fuzzy_lower_threshold(num)}
                if op == "<":
                    return {f"{field}_lesser": num}
                if op == "<=":
                    return {f"{field}_lesser": self._fuzzy_upper_threshold(num)}
            else:
                if op == ">":
                    return {f"{field}_greater": num}
                if op == ">=":
                    return {f"{field}_greater": num - 1}
                if op == "<":
                    return {f"{field}_lesser": num}
                if op == "<=":
                    return {f"{field}_lesser": num + 1}
            return None

        if value_type == "fuzzy_date":
            parsed = self._parse_fuzzy_date_int(raw_value)
        else:
            parsed = self._parse_int_value(raw_value)
        if parsed is None:
            return None
        return {field: parsed}

    @staticmethod
    def _scalar_cmp(column, operator: str, num: int):
        """Builds a scalar comparison expression for numeric columns."""
        if operator == ">":
            return column > num
        if operator == ">=":
            return column >= num
        if operator == "<":
            return column < num
        if operator == "<=":
            return column <= num
        return None

    def _filter_scalar(
        self,
        ctx,
        column,
        cmp_filter: tuple[str, int] | None,
        range_filter: tuple[int, int] | None,
        raw_value: str,
        values: tuple[str, ...] | None = None,
    ) -> set[int]:
        """Filters scalar columns using comparison or range syntax."""
        stmt = select(AniMap.anilist_id)
        if values:
            seen: set[int] = set()
            numbers: list[int] = []
            for raw in values:
                try:
                    num = int(raw)
                except (TypeError, ValueError):
                    return set()
                if num in seen:
                    continue
                seen.add(num)
                numbers.append(num)
            if not numbers:
                return set()
            return self._fetch_ids(ctx, stmt.where(column.in_(numbers)))
        if cmp_filter:
            op, num = cmp_filter
            cond = self._scalar_cmp(column, op, num)
            if cond is None:
                return set()
            return self._fetch_ids(ctx, stmt.where(cond))
        if range_filter:
            lo, hi = range_filter
            return self._fetch_ids(ctx, stmt.where(and_(column >= lo, column <= hi)))
        try:
            num = int(raw_value)
        except Exception:
            return set()
        return self._fetch_ids(ctx, stmt.where(column == num))

    def _filter_json_array(
        self,
        ctx,
        column,
        numeric: bool,
        raw_value: str,
        cmp_filter: tuple[str, int] | None,
        range_filter: tuple[int, int] | None,
        values: tuple[str, ...] | None = None,
    ) -> set[int]:
        """Filters JSON array columns using scalar or wildcard logic."""
        stmt = select(AniMap.anilist_id)
        if numeric:
            if values:
                seen: set[int] = set()
                nums: list[int] = []
                for raw in values:
                    try:
                        val = int(raw)
                    except (TypeError, ValueError):
                        return set()
                    if val in seen:
                        continue
                    seen.add(val)
                    nums.append(val)
                if not nums:
                    return set()
                return self._fetch_ids(
                    ctx, stmt.where(json_array_contains(column, nums))
                )
            if cmp_filter:
                op, num = cmp_filter
                return self._fetch_ids(
                    ctx, stmt.where(json_array_compare(column, op, num))
                )
            if range_filter:
                lo, hi = range_filter
                return self._fetch_ids(
                    ctx, stmt.where(json_array_between(column, lo, hi))
                )
            try:
                num = int(raw_value)
            except Exception:
                return set()
            return self._fetch_ids(ctx, stmt.where(json_array_contains(column, [num])))
        text = raw_value
        if values:
            if not any(self._has_wildcards(val) for val in values):
                unique_values = list(dict.fromkeys(values))
                if not unique_values:
                    return set()
                return self._fetch_ids(
                    ctx, stmt.where(json_array_contains(column, unique_values))
                )
            conditions = []
            for val in values:
                if self._has_wildcards(val):
                    conditions.append(json_array_like(column, val))
                else:
                    conditions.append(json_array_contains(column, [val]))
            if not conditions:
                return set()
            return self._fetch_ids(ctx, stmt.where(or_(*conditions)))
        if self._has_wildcards(text):
            return self._fetch_ids(ctx, stmt.where(json_array_like(column, text)))
        return self._fetch_ids(ctx, stmt.where(json_array_contains(column, [text])))

    def _filter_json_dict(
        self,
        ctx,
        column,
        raw_value: str,
        values: tuple[str, ...] | None = None,
    ) -> set[int]:
        """Filters JSON dictionary columns using key/value lookups."""
        if values:
            conditions: list[Any] = []
            for val in values:
                if self._has_wildcards(val):
                    conditions.append(json_dict_key_like(column, val))
                    conditions.append(json_dict_value_like(column, val))
                else:
                    if val != "":
                        conditions.append(json_dict_has_key(column, val))
                    conditions.append(json_dict_has_value(column, val))
            if not conditions:
                return set()
            stmt = select(AniMap.anilist_id).where(or_(*conditions))
            return self._fetch_ids(ctx, stmt)
        text = raw_value
        conditions: list[Any] = []
        if self._has_wildcards(text):
            conditions.append(json_dict_key_like(column, text))
            conditions.append(json_dict_value_like(column, text))
        else:
            if text != "":
                conditions.append(json_dict_has_key(column, text))
            conditions.append(json_dict_has_value(column, text))
        if not conditions:
            return set()
        stmt = select(AniMap.anilist_id).where(or_(*conditions))
        return self._fetch_ids(ctx, stmt)

    @staticmethod
    def _non_empty_json_object(column):
        """Builds a predicate ensuring a JSON object column contains entries."""
        return and_(
            column.is_not(None),
            func.json_type(column) == "object",
            exists(select(1).select_from(func.json_each(column))),
        )

    def _resolve_has(self, ctx, value: str) -> set[int]:
        """Evaluates ``has`` filters and returns matching identifiers."""
        norm = value.strip().lower()
        if norm in ("anilist", "id"):
            return self._fetch_ids(ctx, select(AniMap.anilist_id))
        conditions = {
            "anidb": AniMap.anidb_id.is_not(None),
            "imdb": json_array_exists(AniMap.imdb_id),
            "mal": json_array_exists(AniMap.mal_id),
            "tmdb_movie": json_array_exists(AniMap.tmdb_movie_id),
            "tmdb_show": AniMap.tmdb_show_id.is_not(None),
            "tvdb": AniMap.tvdb_id.is_not(None),
            "tmdb_mappings": self._non_empty_json_object(AniMap.tmdb_mappings),
            "tvdb_mappings": self._non_empty_json_object(AniMap.tvdb_mappings),
        }
        cond = conditions.get(norm)
        if cond is None:
            return set()
        return self._fetch_ids(ctx, select(AniMap.anilist_id).where(cond))

    @staticmethod
    def _has_wildcards(s: str) -> bool:
        """Checks whether a search string includes wildcard characters."""
        return "*" in s or "?" in s

    @staticmethod
    def _collect_provenance(ctx, anilist_ids: Iterable[int]) -> dict[int, list[str]]:
        """Collects provenance sources for the provided AniList identifiers."""
        ids = [int(aid) for aid in anilist_ids]
        result: dict[int, list[str]] = {aid: [] for aid in ids}
        if not ids:
            return result
        rows = ctx.session.execute(
            select(
                AniMapProvenance.anilist_id,
                AniMapProvenance.n,
                AniMapProvenance.source,
            )
            .where(AniMapProvenance.anilist_id.in_(ids))
            .order_by(
                AniMapProvenance.anilist_id.asc(),
                AniMapProvenance.n.asc(),
            )
        ).all()
        for aid, _n, src in rows:
            result.setdefault(int(aid), []).append(src)
        return result

    def _is_custom_source(self, sources: list[str]) -> bool:
        """Determines whether the latest provenance source is a custom entry."""
        if not sources:
            return False
        last_src = sources[-1]
        if last_src is None:
            return False
        if self.upstream_url:
            return last_src != self.upstream_url
        return True

    def _build_item(
        self,
        anilist_id: int,
        animap: AniMap | None,
        sources: list[str],
    ) -> dict[str, Any]:
        """Builds a response item for list endpoints."""
        item = {
            "anilist_id": anilist_id,
            "custom": self._is_custom_source(sources),
            "sources": sources,
        }
        if not animap:
            return item
        item.update(
            {
                "anidb_id": animap.anidb_id,
                "imdb_id": animap.imdb_id,
                "mal_id": animap.mal_id,
                "tmdb_movie_id": animap.tmdb_movie_id,
                "tmdb_show_id": animap.tmdb_show_id,
                "tvdb_id": animap.tvdb_id,
                "tmdb_mappings": animap.tmdb_mappings,
                "tvdb_mappings": animap.tvdb_mappings,
            }
        )
        return item

    async def get_mapping(
        self,
        anilist_id: int,
        *,
        with_anilist: bool = False,
    ) -> dict[str, Any]:
        """Fetch a single mapping entry by AniList identifier.

        Args:
            anilist_id (int): AniList identifier to retrieve.
            with_anilist (bool): Include AniList metadata in the response.

        Returns:
            dict[str, Any]: Mapping payload suitable for API responses.

        Raises:
            MappingNotFoundError: If no mapping exists for the identifier.
        """
        with db() as ctx:
            animap = ctx.session.get(AniMap, int(anilist_id))
            if animap is None:
                raise MappingNotFoundError("Mapping not found")

            sources = self._collect_provenance(ctx, [anilist_id]).get(anilist_id, [])
            item = self._build_item(anilist_id, animap, sources)

        if with_anilist:
            anilist_client = await get_app_state().ensure_public_anilist()
            medias = await anilist_client.batch_get_anime([int(anilist_id)])
            media_map = {m.id: m for m in medias}
            media = media_map.get(int(anilist_id))
            if media:
                item["anilist"] = {
                    field: getattr(media, field)
                    for field in AniListMetadata.model_fields
                    if hasattr(media, field)
                }
            else:
                item["anilist"] = None

        return item

    @staticmethod
    def _load_animaps(ctx, anilist_ids: Iterable[int]) -> dict[int, AniMap]:
        """Loads mapping models keyed by AniList identifier."""
        ids = list({int(aid) for aid in anilist_ids})
        if not ids:
            return {}
        result: dict[int, AniMap] = {}
        for animap in ctx.session.execute(
            select(AniMap).where(AniMap.anilist_id.in_(ids))
        ).scalars():
            result[animap.anilist_id] = animap
        return result

    async def list_mappings(
        self,
        *,
        page: int,
        per_page: int,
        q: str | None,
        custom_only: bool,
        with_anilist: bool,
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List mappings with optional booru-like query.

        Args:
            page (int): 1-based page number.
            per_page (int): Number of items per page.
            q (str | None): Booru-like query string.
            custom_only (bool): Include only custom mappings.
            with_anilist (bool): Include AniList metadata.
            cancel_check (Callable[[], Awaitable[bool]] | None): Async
                callback returning True when the caller has cancelled the
                request.

        Returns:
            tuple[list[dict[str, Any]], int]: The list of mappings and the total count.
        """

        async def ensure_not_cancelled() -> None:
            task = asyncio.current_task()
            if task and task.cancelled():
                raise asyncio.CancelledError
            if cancel_check and await cancel_check():
                raise asyncio.CancelledError

        await ensure_not_cancelled()
        upstream_url = self.upstream_url

        async def resolve_bare_term(term: str) -> list[int]:
            """Resolve a bare AniList search term using filter-based search."""
            await ensure_not_cancelled()
            client = await get_app_state().ensure_public_anilist()
            text = self._normalize_text_query(term)
            if not text:
                return []
            try:
                ids = await client.search_media_ids(
                    filters={"search": text},
                    max_results=self._ANILIST_MAX_RESULTS,
                )
            except (AniListFilterError, AniListSearchError):
                raise
            except Exception as exc:
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise AniListSearchError(
                    f"Failed to resolve AniList search term '{term}'"
                ) from exc
            await ensure_not_cancelled()
            return list(dict.fromkeys(ids))

        items: list[dict[str, Any]] = []
        total: int = 0

        with db() as ctx:
            stmt = select(AniMap)
            sub = (
                select(
                    AniMapProvenance.anilist_id,
                    func.max(AniMapProvenance.n).label("maxn"),
                )
                .group_by(AniMapProvenance.anilist_id)
                .subquery()
            )
            stmt = stmt.outerjoin(
                sub,
                sub.c.anilist_id == AniMap.anilist_id,
            )
            stmt = stmt.outerjoin(
                AniMapProvenance,
                and_(
                    AniMapProvenance.anilist_id == sub.c.anilist_id,
                    AniMapProvenance.n == sub.c.maxn,
                ),
            )

            ani_term_nodes: dict[tuple[str, tuple[str, ...]], deque[KeyTerm]] = {}
            term_results: dict[int, set[int]] = {}

            def resolve_db(term: KeyTerm) -> set[int]:
                """Resolve a KeyTerm into matching AniList identifiers."""
                lowered = term.key.lower()
                spec = self._FIELD_MAP.get(lowered)
                if not spec:
                    return set()
                raw_value = term.value if term.quoted else term.value.strip()
                value_parts = term.values
                value_key = value_parts or (raw_value,)

                if spec.kind == QueryFieldKind.DB_SCALAR:
                    if not spec.column:
                        return set()
                    if value_parts:
                        return self._filter_scalar(
                            ctx,
                            spec.column,
                            None,
                            None,
                            "",
                            value_parts,
                        )
                    cmp_filter, range_filter, text_value = self._parse_numeric_filters(
                        raw_value
                    )
                    return self._filter_scalar(
                        ctx, spec.column, cmp_filter, range_filter, text_value
                    )

                if spec.kind == QueryFieldKind.DB_JSON_ARRAY:
                    if not spec.column:
                        return set()
                    if value_parts:
                        return self._filter_json_array(
                            ctx,
                            spec.column,
                            bool(spec.json_array_numeric),
                            "",
                            None,
                            None,
                            value_parts,
                        )
                    cmp_filter, range_filter, text_value = self._parse_numeric_filters(
                        raw_value
                    )
                    return self._filter_json_array(
                        ctx,
                        spec.column,
                        bool(spec.json_array_numeric),
                        text_value,
                        cmp_filter,
                        range_filter,
                    )

                if spec.kind == QueryFieldKind.DB_JSON_DICT:
                    if not spec.column:
                        return set()
                    if value_parts:
                        return self._filter_json_dict(ctx, spec.column, "", value_parts)
                    return self._filter_json_dict(ctx, spec.column, raw_value)

                if spec.kind == QueryFieldKind.DB_HAS:
                    if value_parts:
                        result: set[int] = set()
                        for part in value_parts:
                            result |= self._resolve_has(ctx, part)
                        return result
                    return self._resolve_has(ctx, raw_value)

                if spec.kind in self._ANILIST_KINDS:
                    cache_key = (spec.key, value_key)
                    queue = ani_term_nodes.get(cache_key)
                    if queue:
                        term_node = queue[0]
                        cached = term_results.get(id(term_node))
                        if cached is not None:
                            queue.popleft()
                            return set(cached)
                    return set()

                return set()

            if q and q.strip():
                try:
                    node = parse_query(q)
                except BooruQuerySyntaxError:
                    raise
                except Exception as exc:
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    raise BooruQuerySyntaxError("Invalid query syntax") from exc

                bare_cache: dict[str, list[int]] = {}
                for term in collect_bare_terms(node):
                    await ensure_not_cancelled()
                    bare_cache[term] = await resolve_bare_term(term)

                key_terms = collect_key_terms(node)
                term_filters: dict[int, dict[str, Any]] = {}
                term_specs: dict[int, QueryFieldSpec] = {}
                term_value_texts: dict[int, str] = {}
                term_value_keys: dict[int, tuple[str, ...]] = {}
                individual_cache: dict[tuple[str, tuple[str, ...]], set[int]] = {}
                client = None
                if key_terms:
                    for term in key_terms:
                        await ensure_not_cancelled()
                        spec = self._FIELD_MAP.get(term.key.lower())
                        if not spec or spec.kind not in self._ANILIST_KINDS:
                            continue
                        term_id = id(term)
                        value_text = term.value if term.quoted else term.value.strip()
                        value_parts = term.values or (value_text,)
                        ani_term_nodes.setdefault(
                            (spec.key, value_parts), deque()
                        ).append(term)
                        term_specs[term_id] = spec
                        term_value_texts[term_id] = value_text
                        term_value_keys[term_id] = value_parts
                        term_filters[term_id] = self._build_anilist_term_filters(
                            spec, value_text, term.values
                        )

                    if term_filters:
                        groups = self._collect_anilist_and_groups(node)
                        for group in groups:
                            await ensure_not_cancelled()
                            if not all(id(term) in term_filters for term in group):
                                continue
                            # Combine compatible AniList filters upstream.
                            combined_filters: dict[str, Any] = {}
                            conflict = False
                            for term in group:
                                for fk, fv in term_filters[id(term)].items():
                                    existing = combined_filters.get(fk)
                                    if existing is not None and existing != fv:
                                        conflict = True
                                        break
                                    if existing is None:
                                        combined_filters[fk] = fv
                                if conflict:
                                    break
                            if conflict:
                                # Conflicting constraints yield an empty intersection.
                                for term in group:
                                    term_results.setdefault(id(term), set())
                                continue
                            if client is None:
                                await ensure_not_cancelled()
                                client = await get_app_state().ensure_public_anilist()
                            try:
                                ids = await client.search_media_ids(
                                    filters=combined_filters,
                                    max_results=self._ANILIST_MAX_RESULTS,
                                )
                            except (AniListFilterError, AniListSearchError):
                                raise
                            except Exception as exc:
                                if isinstance(exc, asyncio.CancelledError):
                                    raise
                                terms_desc = ", ".join(
                                    f"{t.key}:{t.value.strip()}" for t in group
                                )
                                raise AniListSearchError(
                                    f"Failed to resolve AniList filter group "
                                    f"'{terms_desc}'"
                                ) from exc
                            result_set = set(ids)
                            for term in group:
                                term_results[id(term)] = result_set

                    for term in key_terms:
                        await ensure_not_cancelled()
                        spec = term_specs.get(id(term))
                        if not spec:
                            continue
                        term_id = id(term)
                        if term_id in term_results:
                            continue
                        value_text = term_value_texts.get(term_id)
                        value_key = term_value_keys.get(term_id)
                        if value_text is None or value_key is None:
                            value_text = (
                                term.value if term.quoted else term.value.strip()
                            )
                            value_key = term.values or (value_text,)
                            term_value_texts[term_id] = value_text
                            term_value_keys[term_id] = value_key
                        filters_dict = term_filters.get(term_id)
                        if filters_dict is None:
                            filters_dict = self._build_anilist_term_filters(
                                spec,
                                value_text,
                                term.values,
                            )
                            term_filters[term_id] = filters_dict
                        cache_key = (spec.key, value_key)
                        cached = individual_cache.get(cache_key)
                        if cached is None:
                            if client is None:
                                await ensure_not_cancelled()
                                client = await get_app_state().ensure_public_anilist()
                            try:
                                ids = await client.search_media_ids(
                                    filters=filters_dict,
                                    max_results=self._ANILIST_MAX_RESULTS,
                                )
                            except (AniListFilterError, AniListSearchError):
                                raise
                            except Exception as exc:
                                if isinstance(exc, asyncio.CancelledError):
                                    raise
                                raise AniListSearchError(
                                    f"Failed to resolve AniList filter "
                                    f"'{spec.key}:{value_text}'"
                                ) from exc
                            cached = set(ids)
                            individual_cache[cache_key] = cached
                        term_results[term_id] = cached

                def anilist_resolver(term: str) -> list[int]:
                    return bare_cache.get(term, [])

                all_ids = self._fetch_ids(ctx, select(AniMap.anilist_id))
                try:
                    eval_res = evaluate(
                        node,
                        db_resolver=resolve_db,
                        anilist_resolver=anilist_resolver,
                        universe_ids=all_ids,
                    )
                except Exception as exc:
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    raise BooruQueryEvaluationError(
                        "Failed to evaluate booru query"
                    ) from exc

                if eval_res.used_bare and eval_res.order_hint:
                    final_ids = sorted(
                        list(eval_res.ids),
                        key=lambda aid: (eval_res.order_hint.get(aid, 10**9), aid),
                    )
                else:
                    final_ids = sorted(list(eval_res.ids))

                await ensure_not_cancelled()
                sources_by_id = self._collect_provenance(ctx, final_ids)
                if custom_only and final_ids:
                    final_ids = [
                        aid
                        for aid in final_ids
                        if self._is_custom_source(sources_by_id.get(aid, []))
                    ]
                sources_by_id = {aid: sources_by_id.get(aid, []) for aid in final_ids}

                total = len(final_ids)
                start = (page - 1) * per_page
                end = start + per_page
                page_ids = final_ids[start:end]

                if page_ids:
                    await ensure_not_cancelled()
                    rows_map = self._load_animaps(ctx, page_ids)
                    items = [
                        self._build_item(
                            aid,
                            rows_map.get(aid),
                            sources_by_id.get(aid, []),
                        )
                        for aid in page_ids
                    ]
                else:
                    items = []
            else:
                await ensure_not_cancelled()
                where_clauses: list[Any] = []
                if custom_only:
                    if upstream_url:
                        where_clauses.append(
                            and_(
                                AniMapProvenance.source.is_not(None),
                                AniMapProvenance.source != upstream_url,
                            )
                        )
                    else:
                        where_clauses.append(AniMapProvenance.source.is_not(None))

                if where_clauses:
                    stmt = stmt.where(and_(*where_clauses))

                count_stmt = select(func.count()).select_from(stmt.subquery())
                total = ctx.session.execute(count_stmt).scalar_one()

                paged_stmt = (
                    stmt.order_by(AniMap.anilist_id.asc())
                    .offset((page - 1) * per_page)
                    .limit(per_page)
                )
                animaps = list(ctx.session.execute(paged_stmt).scalars())
                await ensure_not_cancelled()
                anilist_ids = [animap.anilist_id for animap in animaps]
                sources_by_id = self._collect_provenance(ctx, anilist_ids)
                items = [
                    self._build_item(
                        animap.anilist_id,
                        animap,
                        sources_by_id.get(animap.anilist_id, []),
                    )
                    for animap in animaps
                ]

        # Optionally fetch AniList metadata for page items only.
        if with_anilist and items:
            await ensure_not_cancelled()
            anilist_client = await get_app_state().ensure_public_anilist()
            anilist_ids = [int(it["anilist_id"]) for it in items]
            medias = await anilist_client.batch_get_anime(anilist_ids)
            by_id = {m.id: m for m in medias}
            for it in items:
                await ensure_not_cancelled()
                m = by_id.get(int(it["anilist_id"]))
                if m:
                    it["anilist"] = {
                        k: getattr(m, k)
                        for k in AniListMetadata.model_fields
                        if hasattr(m, k)
                    }
                else:
                    it["anilist"] = None

        await ensure_not_cancelled()
        return items, total


@lru_cache(maxsize=1)
def get_mappings_service() -> MappingsService:
    """Returns the cached singleton instance of the mappings service.

    Returns:
        MappingsService: Shared service instance.
    """
    return MappingsService()
