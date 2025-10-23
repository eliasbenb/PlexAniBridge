"""Mappings service for CRUD operations, listing, and provenance updates."""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

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

    def _set_provenance_custom_last(self, anilist_id: int, custom_src: str) -> None:
        """Replace provenance entries so that custom is the last source.

        Order becomes [upstream_url? (n=0)], custom (n=last)
        """
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

        # List normalization
        for field in ("imdb_id", "mal_id", "tmdb_movie_id"):
            if field in payload:
                v = payload[field]
                if v is None:
                    payload[field] = None
                elif not isinstance(v, list):
                    payload[field] = [v]

        with db() as ctx:
            ctx.session.execute(delete(AniMap).where(AniMap.anilist_id == anilist_id))
            obj = AniMap(**payload)
            ctx.session.add(obj)
            ctx.session.commit()

        af, content = self._load_custom()
        # Preserve $includes if present
        entry = {k: payload[k] for k in payload if k != "anilist_id"}
        content[str(anilist_id)] = entry
        self._dump_custom(af, content)

        self._set_provenance_custom_last(anilist_id, str(af.path))
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
                if k in ("imdb_id", "mal_id", "tmdb_movie_id"):
                    if v is None:
                        setattr(obj, k, None)
                    elif isinstance(v, list):
                        setattr(obj, k, v)
                    else:
                        setattr(obj, k, [v])
                else:
                    setattr(obj, k, v)

            ctx.session.commit()

        # Persist partial overlay in custom file
        af, content = self._load_custom()
        existing = content.get(str(anilist_id))
        entry: dict[str, Any] = existing if isinstance(existing, dict) else {}
        for k, v in partial.items():
            if k == "anilist_id":
                continue
            if k not in AniMap.__table__.columns:
                continue
            else:
                entry[k] = v

        content[str(anilist_id)] = entry
        self._dump_custom(af, content)

        self._set_provenance_custom_last(anilist_id, str(af.path))
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

        af, content = self._load_custom()
        content[str(anilist_id)] = None
        self._dump_custom(af, content)
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
            """Resolve bare term to AniList IDs using AniList search.

            Args:
                term (str): The search term to resolve.

            Returns:
                list[int]: List of matching AniList IDs.
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

        def resolve_db(key: str, value: str) -> set[int]:
            """Resolve and return matching AniList IDs for a key/value pair.

            Args:
                key (str): The field to query (e.g., "anilist", "mal", "imdb", etc.).
                value (str): The value or pattern to match.

            Returns:
                set[int]: Set of matching AniList IDs.
            """

            def _has_wildcards(s: str) -> bool:
                return "*" in s or "?" in s

            with db() as ctx:
                s = select(AniMap.anilist_id)

                def _scalar_cmp(col, op: str, num: int):
                    """Helpers for comparisons on scalar int columns.

                    JSON numeric array comparisons are delegated to utils.sql
                    """
                    if op == ">":
                        return col > num
                    if op == ">=":
                        return col >= num
                    if op == "<":
                        return col < num
                    if op == "<=":
                        return col <= num
                    return None

                m_cmp = re.match(r"^(>=|>|<=|<)(\d+)$", str(value))
                m_rng = re.match(r"^(\d+)\.\.(\d+)$", str(value))
                if key in ("anilist", "id"):
                    try:
                        if m_cmp:
                            num = int(m_cmp.group(2))
                            cond = _scalar_cmp(AniMap.anilist_id, m_cmp.group(1), num)
                            if cond is None:
                                return set()
                            s = s.where(cond)
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        if m_rng:
                            lo, hi = int(m_rng.group(1)), int(m_rng.group(2))
                            s = s.where(
                                and_(AniMap.anilist_id >= lo, AniMap.anilist_id <= hi)
                            )
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        num = int(value)
                    except Exception:
                        return set()
                    s = s.where(AniMap.anilist_id == num)
                elif key == "has":
                    v = str(value or "").strip().lower()
                    if v in ("anilist", "id"):
                        # Every mapping has an AniList id; return all
                        return set(
                            int(r[0])
                            for r in ctx.session.execute(
                                select(AniMap.anilist_id)
                            ).all()
                        )
                    if v == "anidb":
                        s = s.where(AniMap.anidb_id.is_not(None))
                    elif v == "imdb":
                        s = s.where(json_array_exists(AniMap.imdb_id))
                    elif v == "mal":
                        s = s.where(json_array_exists(AniMap.mal_id))
                    elif v == "tmdb_movie":
                        s = s.where(json_array_exists(AniMap.tmdb_movie_id))
                    elif v == "tmdb_show":
                        s = s.where(AniMap.tmdb_show_id.is_not(None))
                    elif v == "tvdb":
                        s = s.where(AniMap.tvdb_id.is_not(None))
                    elif v == "tmdb_mappings":
                        s = s.where(
                            and_(
                                AniMap.tmdb_mappings.is_not(None),
                                func.json_type(AniMap.tmdb_mappings) == "object",
                                exists(
                                    select(1).select_from(
                                        func.json_each(AniMap.tmdb_mappings)
                                    )
                                ),
                            )
                        )
                    elif v == "tvdb_mappings":
                        s = s.where(
                            and_(
                                AniMap.tvdb_mappings.is_not(None),
                                func.json_type(AniMap.tvdb_mappings) == "object",
                                exists(
                                    select(1).select_from(
                                        func.json_each(AniMap.tvdb_mappings)
                                    )
                                ),
                            )
                        )
                    else:
                        return set()
                    return set(int(r[0]) for r in ctx.session.execute(s).all())
                elif key == "anidb":
                    try:
                        if m_cmp:
                            num = int(m_cmp.group(2))
                            cond = _scalar_cmp(AniMap.anidb_id, m_cmp.group(1), num)
                            if cond is None:
                                return set()
                            s = s.where(cond)
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        if m_rng:
                            lo, hi = int(m_rng.group(1)), int(m_rng.group(2))
                            s = s.where(
                                and_(AniMap.anidb_id >= lo, AniMap.anidb_id <= hi)
                            )
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        num = int(value)
                    except Exception:
                        return set()
                    s = s.where(AniMap.anidb_id == num)
                elif key == "imdb":
                    if _has_wildcards(value):
                        s = s.where(json_array_like(AniMap.imdb_id, value))
                    else:
                        s = s.where(json_array_contains(AniMap.imdb_id, [value]))
                elif key == "mal":
                    try:
                        if m_cmp:
                            num = int(m_cmp.group(2))
                            s = s.where(
                                json_array_compare(AniMap.mal_id, m_cmp.group(1), num)
                            )
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        if m_rng:
                            lo, hi = int(m_rng.group(1)), int(m_rng.group(2))
                            s = s.where(json_array_between(AniMap.mal_id, lo, hi))
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        num = int(value)
                    except Exception:
                        return set()
                    s = s.where(json_array_contains(AniMap.mal_id, [num]))
                elif key == "tmdb_movie":
                    try:
                        if m_cmp:
                            num = int(m_cmp.group(2))
                            s = s.where(
                                json_array_compare(
                                    AniMap.tmdb_movie_id, m_cmp.group(1), num
                                )
                            )
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        if m_rng:
                            lo, hi = int(m_rng.group(1)), int(m_rng.group(2))
                            s = s.where(
                                json_array_between(AniMap.tmdb_movie_id, lo, hi)
                            )
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        num = int(value)
                    except Exception:
                        return set()
                    s = s.where(json_array_contains(AniMap.tmdb_movie_id, [num]))
                elif key == "tmdb_show":
                    try:
                        if m_cmp:
                            num = int(m_cmp.group(2))
                            cond = _scalar_cmp(AniMap.tmdb_show_id, m_cmp.group(1), num)
                            if cond is None:
                                return set()
                            s = s.where(cond)
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        if m_rng:
                            lo, hi = int(m_rng.group(1)), int(m_rng.group(2))
                            s = s.where(
                                and_(
                                    AniMap.tmdb_show_id >= lo, AniMap.tmdb_show_id <= hi
                                )
                            )
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        num = int(value)
                    except Exception:
                        return set()
                    s = s.where(AniMap.tmdb_show_id == num)
                elif key == "tvdb":
                    try:
                        if m_cmp:
                            num = int(m_cmp.group(2))
                            cond = _scalar_cmp(AniMap.tvdb_id, m_cmp.group(1), num)
                            if cond is None:
                                return set()
                            s = s.where(cond)
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        if m_rng:
                            lo, hi = int(m_rng.group(1)), int(m_rng.group(2))
                            s = s.where(
                                and_(AniMap.tvdb_id >= lo, AniMap.tvdb_id <= hi)
                            )
                            return set(int(r[0]) for r in ctx.session.execute(s).all())
                        num = int(value)
                    except Exception:
                        num = None
                    tvdb_or: list[Any] = []
                    if num is not None:
                        tvdb_or.append(AniMap.tvdb_id == num)
                    if tvdb_or:
                        s = s.where(or_(*tvdb_or))
                elif key == "tmdb_mappings":
                    if m_cmp:
                        try:
                            num = int(m_cmp.group(2))
                        except Exception:
                            return set()
                        return set()
                    if m_rng:
                        return set()
                    v = str(value)
                    tmdbm_or: list[Any] = []
                    if _has_wildcards(v):
                        tmdbm_or.append(json_dict_key_like(AniMap.tmdb_mappings, v))
                        tmdbm_or.append(json_dict_value_like(AniMap.tmdb_mappings, v))
                    else:
                        # Avoid generating an invalid JSON path like '$.' when empty
                        if v != "":
                            tmdbm_or.append(json_dict_has_key(AniMap.tmdb_mappings, v))
                        tmdbm_or.append(json_dict_has_value(AniMap.tmdb_mappings, v))
                    if not tmdbm_or:
                        return set()
                    s = s.where(or_(*tmdbm_or))
                elif key == "tvdb_mappings":
                    if m_cmp:
                        try:
                            num = int(m_cmp.group(2))
                        except Exception:
                            return set()
                        return set()
                    if m_rng:
                        return set()
                    v = str(value)
                    tvdm_or: list[Any] = []
                    if _has_wildcards(v):
                        tvdm_or.append(json_dict_key_like(AniMap.tvdb_mappings, v))
                        tvdm_or.append(json_dict_value_like(AniMap.tvdb_mappings, v))
                    else:
                        # Avoid generating an invalid JSON path like '$.' when empty
                        if v != "":
                            tvdm_or.append(json_dict_has_key(AniMap.tvdb_mappings, v))
                        tvdm_or.append(json_dict_has_value(AniMap.tvdb_mappings, v))
                    if not tvdm_or:
                        return set()
                    s = s.where(or_(*tvdm_or))
                else:
                    return set()

                return set(int(r[0]) for r in ctx.session.execute(s).all())

        items: list[dict[str, Any]] = []
        total: int = 0

        with db() as ctx:
            stmt = select(AniMap)

            # Join last provenance source
            sub = (
                select(
                    AniMapProvenance.anilist_id,
                    func.max(AniMapProvenance.n).label("maxn"),
                )
                .group_by(AniMapProvenance.anilist_id)
                .subquery()
            )
            stmt = (
                stmt.outerjoin(sub, sub.c.anilist_id == AniMap.anilist_id)
                .outerjoin(
                    AniMapProvenance,
                    and_(
                        AniMapProvenance.anilist_id == sub.c.anilist_id,
                        AniMapProvenance.n == sub.c.maxn,
                    ),
                )
                .add_columns(AniMapProvenance.source)
            )

            # Precedence: id_search > title_search > none
            if q and q.strip():
                node = parse_query(q)

                # Prefetch AniList results for bare terms once (async) and then
                # pass a sync resolver backed by the cache to the evaluator.
                bare_cache: dict[str, list[int]] = {}
                bare_terms = collect_bare_terms(node)
                for term in bare_terms:
                    bare_cache[term] = await resolve_anilist(term)

                def db_resolver(k: str, v: str) -> set[int]:
                    return resolve_db(k, v)

                def anilist_resolver(term: str) -> list[int]:
                    return bare_cache.get(term, [])

                # Build a full-universe id set so negations work relative to all ids.
                all_ids = set(
                    int(r[0])
                    for r in ctx.session.execute(select(AniMap.anilist_id)).all()
                )
                eval_res = evaluate(
                    node,
                    db_resolver=db_resolver,
                    anilist_resolver=anilist_resolver,
                    universe_ids=all_ids,
                )

                final_ids: list[int]
                if eval_res.used_bare and eval_res.order_hint:
                    final_ids = sorted(
                        list(eval_res.ids),
                        key=lambda aid: (eval_res.order_hint.get(aid, 10**9), aid),
                    )
                else:
                    final_ids = sorted(list(eval_res.ids))

                if custom_only and final_ids:
                    # Filter based on provenance
                    sub = (
                        select(
                            AniMapProvenance.anilist_id,
                            func.max(AniMapProvenance.n).label("maxn"),
                        )
                        .where(AniMapProvenance.anilist_id.in_(final_ids))
                        .group_by(AniMapProvenance.anilist_id)
                        .subquery()
                    )
                    last_rows = ctx.session.execute(
                        select(
                            AniMapProvenance.anilist_id, AniMapProvenance.source
                        ).join(
                            sub,
                            and_(
                                AniMapProvenance.anilist_id == sub.c.anilist_id,
                                AniMapProvenance.n == sub.c.maxn,
                            ),
                        )
                    ).all()
                    by_id_src = {int(a): s for a, s in last_rows}
                    final_ids = [
                        aid
                        for aid in final_ids
                        if (src := by_id_src.get(aid))
                        and (
                            src is not None
                            and (not upstream_url or src != upstream_url)
                        )
                    ]

                total = len(final_ids)
                start = (page - 1) * per_page
                end = start + per_page
                page_ids = final_ids[start:end]

                if not page_ids:
                    items = []
                else:
                    rows = ctx.session.execute(
                        select(AniMap).where(AniMap.anilist_id.in_(page_ids))
                    ).all()
                    rows_map: dict[int, AniMap] = {
                        row[0].anilist_id: row[0] for row in rows
                    }

                    prov_rows = ctx.session.execute(
                        select(
                            AniMapProvenance.anilist_id,
                            AniMapProvenance.n,
                            AniMapProvenance.source,
                        )
                        .where(AniMapProvenance.anilist_id.in_(page_ids))
                        .order_by(
                            AniMapProvenance.anilist_id.asc(), AniMapProvenance.n.asc()
                        )
                    ).all()
                    sources_by_id: dict[int, list[str]] = {aid: [] for aid in page_ids}
                    for aid, _n, src in prov_rows:
                        sources_by_id.setdefault(int(aid), []).append(src)

                    # maintain page_ids order
                    for aid in page_ids:
                        obj = rows_map.get(aid)
                        srcs = sources_by_id.get(aid, [])
                        last_src = srcs[-1] if srcs else None
                        is_custom = bool(
                            last_src is not None
                            and (not upstream_url or last_src != upstream_url)
                        )
                        if obj is None:
                            items.append(
                                {
                                    "anilist_id": aid,
                                    "custom": False,
                                    "sources": srcs,
                                }
                            )
                        else:
                            items.append(
                                {
                                    "anilist_id": obj.anilist_id,
                                    "anidb_id": obj.anidb_id,
                                    "imdb_id": obj.imdb_id,
                                    "mal_id": obj.mal_id,
                                    "tmdb_movie_id": obj.tmdb_movie_id,
                                    "tmdb_show_id": obj.tmdb_show_id,
                                    "tvdb_id": obj.tvdb_id,
                                    "tmdb_mappings": obj.tmdb_mappings,
                                    "tvdb_mappings": obj.tvdb_mappings,
                                    "custom": is_custom,
                                    "sources": srcs,
                                }
                            )
            else:
                # No search: list all
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

                stmt = (
                    stmt.order_by(AniMap.anilist_id.asc())
                    .offset((page - 1) * per_page)
                    .limit(per_page)
                )
                rows = ctx.session.execute(stmt).all()

                anilist_ids = [row[0].anilist_id for row in rows]
                sources_by_id: dict[int, list[str]] = {aid: [] for aid in anilist_ids}
                if anilist_ids:
                    prov_rows = ctx.session.execute(
                        select(
                            AniMapProvenance.anilist_id,
                            AniMapProvenance.n,
                            AniMapProvenance.source,
                        )
                        .where(AniMapProvenance.anilist_id.in_(anilist_ids))
                        .order_by(
                            AniMapProvenance.anilist_id.asc(), AniMapProvenance.n.asc()
                        )
                    ).all()
                    for aid, _n, src in prov_rows:
                        sources_by_id.setdefault(aid, []).append(src)

                for row in rows:
                    animap: AniMap = row[0]
                    srcs = sources_by_id.get(animap.anilist_id, [])
                    last_src = srcs[-1] if srcs else None
                    is_custom = bool(
                        last_src is not None
                        and (not upstream_url or last_src != upstream_url)
                    )
                    items.append(
                        {
                            "anilist_id": animap.anilist_id,
                            "anidb_id": animap.anidb_id,
                            "imdb_id": animap.imdb_id,
                            "mal_id": animap.mal_id,
                            "tmdb_movie_id": animap.tmdb_movie_id,
                            "tmdb_show_id": animap.tmdb_show_id,
                            "tvdb_id": animap.tvdb_id,
                            "tmdb_mappings": animap.tmdb_mappings,
                            "tvdb_mappings": animap.tvdb_mappings,
                            "custom": is_custom,
                            "sources": srcs,
                        }
                    )

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
    """Get the singleton instance of the mappings service."""
    return MappingsService()
