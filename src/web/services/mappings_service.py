"""Mappings service for provider-range mapping graph (v3)."""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import and_, func, select

from src.config.database import db
from src.config.settings import get_config
from src.core.animap import MappingDescriptor
from src.exceptions import MappingNotFoundError
from src.models.db.animap import AnimapEntry, AnimapMapping, AnimapProvenance
from src.models.schemas.anilist import Media
from src.web.services.mappings_query_spec import QueryFieldSpec, get_query_field_map
from src.web.state import get_app_state

__all__ = ["MappingsService", "get_mappings_service"]


@dataclass(frozen=True)
class EdgeView:
    """Flattened view of an outgoing mapping edge."""

    target_provider: str
    target_entry_id: str
    target_scope: str
    source_range: str
    destination_range: str | None
    sources: list[str]


@dataclass(frozen=True)
class MappingItem:
    """Flattened mapping entry with outgoing edges."""

    provider: str
    entry_id: str
    scope: str
    edges: list[EdgeView]
    custom: bool
    sources: list[str]
    anilist_id: int | None = None
    anilist: Media | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "provider": self.provider,
            "entry_id": self.entry_id,
            "scope": self.scope,
            "descriptor": f"{self.provider}:{self.entry_id}:{self.scope}",
            "edges": [edge.__dict__ for edge in self.edges],
            "custom": self.custom,
            "sources": self.sources,
            "anilist": self.anilist.model_dump() if self.anilist else None,
        }


class MappingsService:
    """Service to query the v3 mapping graph."""

    def __init__(self) -> None:
        """Initialise mapping service with query specs and upstream URL."""
        self._field_map: Mapping[str, QueryFieldSpec] = get_query_field_map()
        self.upstream_url: str | None = get_config().mappings_url

    def _parse_filters(self, q: str | None) -> list[Any]:
        """Parse simple key:value filters from q string."""
        if not q:
            return []
        filters: list[Any] = []
        for token in q.split():
            if ":" not in token:
                continue
            key, raw_value = token.split(":", 1)
            value = raw_value.strip()
            if not value:
                continue
            spec = self._field_map.get(key)
            if not spec or spec.column is None:
                continue
            if key == "entry_id":
                filters.append(spec.column.like(value.replace("*", "%")))
            else:
                filters.append(spec.column == value)
        return filters

    def _build_item(
        self,
        entry: AnimapEntry,
        edges: Iterable[AnimapMapping],
        provenance: Mapping[int, list[str]],
    ) -> MappingItem:
        edge_views: list[EdgeView] = []
        seen_sources: list[str] = []
        entry_by_id: dict[int, AnimapEntry] = self._fetch_entries_for_edges(edges)

        for edge in edges:
            edge_sources = provenance.get(edge.id, [])
            for src in edge_sources:
                if src not in seen_sources:
                    seen_sources.append(src)

            target = entry_by_id.get(edge.destination_entry_id)
            if not target:
                continue
            edge_views.append(
                EdgeView(
                    target_provider=target.provider,
                    target_entry_id=target.entry_id,
                    target_scope=target.entry_scope,
                    source_range=edge.source_range,
                    destination_range=edge.destination_range,
                    sources=edge_sources,
                )
            )

        custom = (
            any(src != self.upstream_url for src in seen_sources)
            if seen_sources
            else False
        )

        anilist_id = self._resolve_anilist_id(entry, entry_by_id, edges)
        return MappingItem(
            provider=entry.provider,
            entry_id=entry.entry_id,
            scope=entry.entry_scope,
            edges=edge_views,
            custom=custom,
            sources=seen_sources,
            anilist_id=anilist_id,
        )

    def _resolve_anilist_id(
        self,
        entry: AnimapEntry,
        entry_by_id: Mapping[int, AnimapEntry],
        edges: Iterable[AnimapMapping],
    ) -> int | None:
        """Pick the first AniList identifier available for a mapping entry."""

        def _to_int(value: str | None) -> int | None:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        if entry.provider == "anilist":
            return _to_int(entry.entry_id)

        for edge in edges:
            target = entry_by_id.get(edge.destination_entry_id)
            if target and target.provider == "anilist":
                aid = _to_int(target.entry_id)
                if aid is not None:
                    return aid

        return None

    async def _attach_anilist_metadata(
        self, items: list[MappingItem]
    ) -> list[MappingItem]:
        """Fetch AniList metadata for items with a resolvable AniList ID."""
        seen_ids: set[int] = set()
        anilist_ids: list[int] = []
        for item in items:
            if item.anilist_id is None:
                continue
            if item.anilist_id not in seen_ids:
                seen_ids.add(item.anilist_id)
                anilist_ids.append(item.anilist_id)

        if not anilist_ids:
            return items

        client = await get_app_state().ensure_public_anilist()
        metadata = await client.batch_get_anime(anilist_ids)
        by_id = {m.id: m for m in metadata}

        return [
            replace(item, anilist=by_id.get(item.anilist_id or -1)) for item in items
        ]

    def _fetch_entries_for_edges(
        self, edges: Iterable[AnimapMapping]
    ) -> dict[int, AnimapEntry]:
        ids: set[int] = set()
        for edge in edges:
            ids.add(edge.source_entry_id)
            ids.add(edge.destination_entry_id)
        if not ids:
            return {}
        with db() as ctx:
            rows = (
                ctx.session.execute(select(AnimapEntry).where(AnimapEntry.id.in_(ids)))
                .scalars()
                .all()
            )
        return {row.id: row for row in rows}

    async def list_mappings(
        self,
        *,
        page: int,
        per_page: int,
        q: str | None,
        custom_only: bool,
        with_anilist: bool = False,
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List mapping entries with pagination and optional filters.

        Args:
            page (int): The page number to retrieve.
            per_page (int): The number of items per page.
            q (str | None): Optional query string with key:value filters.
            custom_only (bool): Whether to include only custom mappings.
            with_anilist (bool): Whether to attach AniList metadata.
            cancel_check (Callable[[], Awaitable[bool]] | None): Optional cancellation
                check.

        Returns:
            tuple[list[dict[str, Any]], int]: A tuple of the list of mapping items
                and the total count.
        """
        filters = self._parse_filters(q)
        with db() as ctx:
            base_stmt = select(AnimapEntry)
            if filters:
                base_stmt = base_stmt.where(and_(*filters))

            total = ctx.session.execute(
                select(func.count()).select_from(base_stmt.subquery())
            ).scalar_one()

            entries = (
                ctx.session.execute(
                    base_stmt.order_by(AnimapEntry.provider, AnimapEntry.entry_id)
                    .offset((page - 1) * per_page)
                    .limit(per_page)
                )
                .scalars()
                .all()
            )

            if not entries:
                return [], 0

            entry_ids = [entry.id for entry in entries]
            edge_rows = (
                ctx.session.execute(
                    select(AnimapMapping).where(
                        AnimapMapping.source_entry_id.in_(entry_ids)
                    )
                )
                .scalars()
                .all()
            )
            edge_ids = [edge.id for edge in edge_rows]
            prov_rows = (
                ctx.session.execute(
                    select(AnimapProvenance).where(
                        AnimapProvenance.mapping_id.in_(edge_ids)
                    )
                )
                .scalars()
                .all()
            )
            provenance: dict[int, list[str]] = {}
            for row in prov_rows:
                provenance.setdefault(row.mapping_id, []).append(row.source)

            items: list[MappingItem] = []
            for entry in entries:
                entry_edges = [e for e in edge_rows if e.source_entry_id == entry.id]
                item = self._build_item(entry, entry_edges, provenance)
                if custom_only and not item.custom:
                    continue
                items.append(item)

        if with_anilist:
            items = await self._attach_anilist_metadata(items)

        return [it.to_dict() for it in items], total

    async def get_mapping(self, descriptor: str) -> dict[str, Any]:
        """Return a single mapping entry by descriptor.

        Args:
            descriptor (str): The mapping descriptor to fetch.

        Returns:
            dict[str, Any]: The mapping item.
        """
        parsed = MappingDescriptor.parse(descriptor)
        with db() as ctx:
            entry = (
                ctx.session.execute(
                    select(AnimapEntry).where(
                        AnimapEntry.provider == parsed.provider,
                        AnimapEntry.entry_id == parsed.entry_id,
                        AnimapEntry.entry_scope == parsed.scope,
                    )
                )
                .scalars()
                .first()
            )
            if not entry:
                raise MappingNotFoundError("Mapping not found")

            edge_rows = (
                ctx.session.execute(
                    select(AnimapMapping).where(
                        AnimapMapping.source_entry_id == entry.id
                    )
                )
                .scalars()
                .all()
            )
            edge_ids = [edge.id for edge in edge_rows]
            prov_rows = (
                ctx.session.execute(
                    select(AnimapProvenance).where(
                        AnimapProvenance.mapping_id.in_(edge_ids)
                    )
                )
                .scalars()
                .all()
            )
            provenance: dict[int, list[str]] = {}
            for row in prov_rows:
                provenance.setdefault(row.mapping_id, []).append(row.source)

            item = self._build_item(entry, edge_rows, provenance)
            return item.to_dict()


_mappings_service: MappingsService | None = None


def get_mappings_service() -> MappingsService:
    """Return a singleton mappings service instance.

    Returns:
        MappingsService: The singleton service instance.
    """
    global _mappings_service
    if _mappings_service is None:
        _mappings_service = MappingsService()
    return _mappings_service
