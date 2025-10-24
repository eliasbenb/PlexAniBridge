"""Mappings service for CRUD operations, listing, and provenance updates."""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

import yaml
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.sql import exists

from src import log
from src.config.database import db
from src.config.settings import get_config
from src.core.mappings import MappingsClient
from src.exceptions import MissingAnilistIdError, UnsupportedMappingFileExtensionError
from src.models.db.animap import AniMap
from src.models.db.provenance import AniMapProvenance
from src.models.schemas.anilist import MediaWithoutList as AniListMetadata
from src.utils.booru_query import collect_bare_terms, evaluate, parse_query
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
from src.web.state import get_app_state

__all__ = ["MappingsService", "get_mappings_service"]


@dataclass
class _ActiveFile:
    path: Path
    ext: str


class MappingsService:
    """Service to manage custom mappings and DB provenance."""

    _LIST_FIELDS: ClassVar[tuple[str, ...]] = ("imdb_id", "mal_id", "tmdb_movie_id")
    _SCALAR_FIELDS: ClassVar[dict[str, Any]] = {
        "anilist": AniMap.anilist_id,
        "id": AniMap.anilist_id,
        "anidb": AniMap.anidb_id,
        "tmdb_show": AniMap.tmdb_show_id,
        "tvdb": AniMap.tvdb_id,
    }
    _JSON_ARRAY_FIELDS: ClassVar[dict[str, tuple[Any, bool]]] = {
        "imdb": (AniMap.imdb_id, False),
        "mal": (AniMap.mal_id, True),
        "tmdb_movie": (AniMap.tmdb_movie_id, True),
    }
    _CMP_RE: ClassVar[re.Pattern[str]] = re.compile(r"^(>=|>|<=|<)(\d+)$")
    _RANGE_RE: ClassVar[re.Pattern[str]] = re.compile(r"^(\d+)\.\.(\d+)$")

    def __init__(self) -> None:
        """Initialize service with config and paths."""
        _config = get_config()
        self.data_path: Path = _config.data_path
        self.upstream_url: str | None = _config.mappings_url

    def _active_custom_file(self) -> _ActiveFile:
        """Determine the active custom mappings file (json/yaml/yml)."""
        for fname in MappingsClient.MAPPING_FILES:
            p = (self.data_path / fname).resolve()
            if p.exists():
                return _ActiveFile(path=p, ext=p.suffix.lstrip("."))
        p = (self.data_path / "mappings.custom.yaml").resolve()
        return _ActiveFile(path=p, ext="yaml")

    def _load_custom(self) -> tuple[_ActiveFile, dict[str, Any]]:
        """Load and parse the active custom mappings file."""
        af = self._active_custom_file()
        if not af.path.exists():
            return af, {}

        try:
            if af.ext == "json":
                return af, json.loads(af.path.read_text(encoding="utf-8"))
            elif af.ext in ("yaml", "yml"):
                return af, yaml.safe_load(af.path.read_text(encoding="utf-8")) or {}
            raise UnsupportedMappingFileExtensionError(
                f"Unsupported file extension: {af.ext}"
            )
        except Exception:
            return af, {}

    def _dump_custom(self, af: _ActiveFile, content: dict[str, Any]) -> None:
        """Dump content to the active custom mappings file."""
        af.path.parent.mkdir(parents=True, exist_ok=True)
        if af.ext == "json":
            af.path.write_text(
                json.dumps(content, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        elif af.ext in ("yaml", "yml"):
            af.path.write_text(
                yaml.safe_dump(content, sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )
        else:
            raise UnsupportedMappingFileExtensionError(
                f"Unsupported file extension: {af.ext}"
            )

    def _update_custom_file(
        self,
        anilist_id: int,
        entry: Any,
        *,
        update_provenance: bool = True,
        active_file: _ActiveFile | None = None,
        content: dict[str, Any] | None = None,
    ) -> None:
        """Persists a mapping entry and optionally updates provenance ordering."""
        if active_file and content is not None:
            af, data = active_file, content
        else:
            af, data = self._load_custom()
        data[str(anilist_id)] = entry
        self._dump_custom(af, data)
        if update_provenance:
            self._set_provenance_custom_last(anilist_id, str(af.path))

    @staticmethod
    def _normalize_list_value(value: Any) -> list[Any] | None:
        """Normalizes scalar or iterable inputs into list form."""
        if value is None:
            return None
        return value if isinstance(value, list) else [value]

    def _normalize_list_fields(
        self, payload: dict[str, Any], fields: Iterable[str] | None = None
    ) -> None:
        """Applies list normalization across the provided payload fields."""
        for field in fields or self._LIST_FIELDS:
            if field in payload:
                payload[field] = self._normalize_list_value(payload[field])

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
    ) -> set[int]:
        """Filters scalar columns using comparison or range syntax."""
        stmt = select(AniMap.anilist_id)
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
    ) -> set[int]:
        """Filters JSON array columns using scalar or wildcard logic."""
        stmt = select(AniMap.anilist_id)
        if numeric:
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
        if self._has_wildcards(text):
            return self._fetch_ids(ctx, stmt.where(json_array_like(column, text)))
        return self._fetch_ids(ctx, stmt.where(json_array_contains(column, [text])))

    def _filter_json_dict(self, ctx, column, raw_value: str) -> set[int]:
        """Filters JSON dictionary columns using key/value lookups."""
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

    def _set_provenance_custom_last(self, anilist_id: int, custom_src: str) -> None:
        """Replace provenance entries so that custom is the last source."""
        with db() as ctx:
            if ctx.session.get(AniMap, anilist_id) is None:
                return

            ctx.session.execute(
                delete(AniMapProvenance).where(
                    AniMapProvenance.anilist_id == anilist_id
                )
            )

            n = 0
            rows: list[AniMapProvenance] = []
            if self.upstream_url:
                rows.append(
                    AniMapProvenance(
                        anilist_id=anilist_id, n=n, source=self.upstream_url
                    )
                )
                n += 1

            rows.append(
                AniMapProvenance(anilist_id=anilist_id, n=n, source=str(custom_src))
            )
            ctx.session.add_all(rows)
            ctx.session.commit()

    def replace_mapping(self, mapping: dict[str, Any]) -> AniMap:
        """Replace DB row with provided mapping and persist full mapping in custom file.

        Args:
            mapping (dict[str, Any]): Full mapping dict including anilist_id.

        Returns:
            AniMap: The up-to-date DB model.

        Raises:
            MissingAnilistIdError: If anilist_id is missing.
            UnsupportedMappingFileExtensionError: If the custom file extension is
                unsupported.
        """
        if "anilist_id" not in mapping:
            raise MissingAnilistIdError("anilist_id is required")
        anilist_id = int(mapping["anilist_id"])
        log.info(f"Replacing mapping for anilist_id={anilist_id}")

        defaults = {c.name: None for c in AniMap.__table__.columns}
        payload: dict[str, Any] = {**defaults, **mapping, "anilist_id": anilist_id}

        self._normalize_list_fields(payload)

        with db() as ctx:
            ctx.session.execute(delete(AniMap).where(AniMap.anilist_id == anilist_id))
            obj = AniMap(**payload)
            ctx.session.add(obj)
            ctx.session.commit()

        entry = {k: payload[k] for k in payload if k != "anilist_id"}
        self._update_custom_file(anilist_id, entry)
        log.success(f"Replaced mapping for anilist_id={anilist_id}")

        return obj

    def upsert_mapping(self, anilist_id: int, partial: dict[str, Any]) -> AniMap:
        """Upsert DB row applying only provided fields and save partial overlay.

        Args:
            anilist_id (int): The AniList ID of the entry to upsert.
            partial (dict[str, Any]): Partial mapping dict with fields to update.

        Returns:
            AniMap: The up-to-date DB model.

        Raises:
            UnsupportedMappingFileExtensionError: If the custom file extension is
                unsupported.
        """
        log.info(f"Upserting mapping for anilist_id={anilist_id}")
        updates: dict[str, Any] = {}
        with db() as ctx:
            obj = ctx.session.get(AniMap, anilist_id)
            if not obj:
                defaults = {c.name: None for c in AniMap.__table__.columns}
                obj = AniMap(**{**defaults, "anilist_id": anilist_id})
                ctx.session.add(obj)

            for k, v in partial.items():
                if k == "anilist_id":
                    continue
                if k not in AniMap.__table__.columns:
                    continue
                if k in self._LIST_FIELDS:
                    normalized = self._normalize_list_value(v)
                    setattr(obj, k, normalized)
                    updates[k] = normalized
                else:
                    setattr(obj, k, v)
                    updates[k] = v

            ctx.session.commit()

        af, content = self._load_custom()
        existing = content.get(str(anilist_id))
        entry: dict[str, Any] = existing.copy() if isinstance(existing, dict) else {}
        entry.update(updates)
        self._update_custom_file(
            anilist_id,
            entry,
            active_file=af,
            content=content,
        )
        log.success(f"Upserted mapping for anilist_id={anilist_id}")

        return obj

    def delete_mapping(self, anilist_id: int) -> None:
        """Delete mapping from DB and shadow upstream by setting null in custom file.

        Args:
            anilist_id (int): The AniList ID of the entry to delete.

        Raises:
            UnsupportedMappingFileExtensionError: If the custom file extension is
                unsupported.
        """
        log.info(f"Deleting mapping for anilist_id={anilist_id}")
        with db() as ctx:
            ctx.session.execute(
                delete(AniMapProvenance).where(
                    AniMapProvenance.anilist_id == anilist_id
                )
            )
            ctx.session.execute(delete(AniMap).where(AniMap.anilist_id == anilist_id))
            ctx.session.commit()

        self._update_custom_file(
            anilist_id,
            None,
            update_provenance=False,
        )
        log.success(f"Deleted mapping for anilist_id={anilist_id}")

    async def list_mappings(
        self,
        *,
        page: int,
        per_page: int,
        q: str | None,
        custom_only: bool,
        with_anilist: bool,
    ) -> tuple[list[dict[str, Any]], int]:
        """List mappings with optional booru-like query.

        Args:
            page (int): 1-based page number.
            per_page (int): Number of items per page.
            q (str | None): Booru-like query string.
            custom_only (bool): Include only custom mappings.
            with_anilist (bool): Include AniList metadata.

        Returns:
            tuple[list[dict[str, Any]], int]: The list of mappings and the total count.
        """
        upstream_url = self.upstream_url

        async def resolve_anilist(term: str) -> list[int]:
            """Resolves a search term to AniList identifiers via the public client.

            Args:
                term (str): User supplied search term.

            Returns:
                list[int]: Matching AniList identifiers in discovery order.
            """
            client = await get_app_state().ensure_public_anilist()
            search_limit = 50  # Max results AniList API allows
            ids: list[int] = []
            seen: set[int] = set()
            async for m in client.search_anime(
                term, is_movie=None, episodes=None, limit=search_limit
            ):
                aid = int(m.id)
                if aid not in seen:
                    ids.append(aid)
                    seen.add(aid)
            return ids

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

            def resolve_db(key: str, value: str) -> set[int]:
                """Resolves a query key/value pair to matching AniList identifiers.

                Args:
                    key (str): Field name provided by the booru query.
                    value (str): Raw query value including operators or wildcards.

                Returns:
                    set[int]: AniList identifiers matching the filter.
                """
                cmp_filter, range_filter, text_value = self._parse_numeric_filters(
                    value
                )
                lowered = key.lower()
                if lowered in self._SCALAR_FIELDS:
                    column = self._SCALAR_FIELDS[lowered]
                    return self._filter_scalar(
                        ctx, column, cmp_filter, range_filter, text_value
                    )
                if lowered == "has":
                    return self._resolve_has(ctx, text_value)
                if lowered in self._JSON_ARRAY_FIELDS:
                    column, numeric = self._JSON_ARRAY_FIELDS[lowered]
                    return self._filter_json_array(
                        ctx, column, numeric, text_value, cmp_filter, range_filter
                    )
                if lowered in ("tmdb_mappings", "tvdb_mappings"):
                    if cmp_filter or range_filter:
                        return set()
                    column = (
                        AniMap.tmdb_mappings
                        if lowered == "tmdb_mappings"
                        else AniMap.tvdb_mappings
                    )
                    return self._filter_json_dict(ctx, column, text_value)
                return set()

            if q and q.strip():
                node = parse_query(q)

                bare_cache: dict[str, list[int]] = {}
                for term in collect_bare_terms(node):
                    bare_cache[term] = await resolve_anilist(term)

                def db_resolver(k: str, v: str) -> set[int]:
                    return resolve_db(k, v)

                def anilist_resolver(term: str) -> list[int]:
                    return bare_cache.get(term, [])

                all_ids = self._fetch_ids(ctx, select(AniMap.anilist_id))
                eval_res = evaluate(
                    node,
                    db_resolver=db_resolver,
                    anilist_resolver=anilist_resolver,
                    universe_ids=all_ids,
                )

                if eval_res.used_bare and eval_res.order_hint:
                    final_ids = sorted(
                        list(eval_res.ids),
                        key=lambda aid: (eval_res.order_hint.get(aid, 10**9), aid),
                    )
                else:
                    final_ids = sorted(list(eval_res.ids))

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
            anilist_client = await get_app_state().ensure_public_anilist()
            anilist_ids = [int(it["anilist_id"]) for it in items]
            medias = await anilist_client.batch_get_anime(anilist_ids)
            by_id = {m.id: m for m in medias}
            for it in items:
                m = by_id.get(int(it["anilist_id"]))
                if m:
                    it["anilist"] = {
                        k: getattr(m, k)
                        for k in AniListMetadata.model_fields
                        if hasattr(m, k)
                    }
                else:
                    it["anilist"] = None

        return items, total


@lru_cache(maxsize=1)
def get_mappings_service() -> MappingsService:
    """Returns the cached singleton instance of the mappings service.

    Returns:
        MappingsService: Shared service instance.
    """
    return MappingsService()
