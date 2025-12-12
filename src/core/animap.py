"""Animap client for v3 provider-range mappings."""

import json
import re
from dataclasses import dataclass
from hashlib import md5
from itertools import batched
from pathlib import Path
from typing import NamedTuple

from sqlalchemy.orm import Session
from sqlalchemy.sql import delete, select, tuple_

from src import log
from src.config.database import db
from src.core.mappings import MappingsClient
from src.models.db.animap import AnimapEntry, AnimapMapping, AnimapProvenance
from src.models.db.housekeeping import Housekeeping

__all__ = ["AnimapClient", "AnimapEdge", "MappingDescriptor", "MappingGraph"]


class AnimapEdge(NamedTuple):
    """Directed mapping between two provider entries with episode ranges."""

    source: MappingDescriptor
    destination: MappingDescriptor
    source_range: str
    destination_range: str | None


@dataclass(frozen=True, slots=True)
class MappingGraph:
    """Subset of the mapping graph relevant to a lookup request."""

    edges: tuple[AnimapEdge, ...]

    def descriptors(self) -> tuple[MappingDescriptor, ...]:
        """Return unique descriptors referenced by the edges.

        Returns:
            tuple[MappingDescriptor, ...]: Ordered unique descriptors.
        """
        seen: set[str] = set()
        ordered: list[MappingDescriptor] = []
        for edge in self.edges:
            for descriptor in (edge.source, edge.destination):
                key = descriptor.key()
                if key in seen:
                    continue
                seen.add(key)
                ordered.append(descriptor)
        return tuple(ordered)


@dataclass(frozen=True, slots=True)
class MappingDescriptor:
    """Provider/entry/scope descriptor (e.g., anilist:849:s1)."""

    provider: str
    entry_id: str
    scope: str

    _PATTERN = re.compile(
        r"^(?P<provider>[A-Za-z_][A-Za-z0-9_]*):(?P<entry>[^:]+):(?P<scope>s[0-9]+|movie)$"
    )

    @classmethod
    def parse(cls, raw: str) -> MappingDescriptor:
        """Parse a descriptor string into its components.

        Args:
            raw (str): Raw descriptor string.

        Returns:
            MappingDescriptor: Parsed descriptor object.
        """
        match = cls._PATTERN.match(raw)
        if not match:
            raise ValueError("Invalid mapping descriptor")
        return cls(
            provider=match.group("provider"),
            entry_id=match.group("entry"),
            scope=match.group("scope"),
        )

    def key(self) -> str:
        """Return the canonical descriptor key string."""
        return f"{self.provider}:{self.entry_id}:{self.scope}"

    def __str__(self) -> str:
        """Human-readable representation used in logs."""
        return self.key()


class AnimapClient:
    """Client for managing Animap data using the v3 range-based schema."""

    _SQLITE_SAFE_VARIABLES = 900

    def __init__(self, data_path: Path, upstream_url: str | None) -> None:
        """Create a new Animap client."""
        self.data_path = data_path
        self.upstream_url = upstream_url
        self.mappings_client = MappingsClient(data_path, upstream_url)
        self._edge_cache: tuple[AnimapEdge, ...] = tuple()
        self._adjacency: dict[tuple[str, str], tuple[int, ...]] = {}
        self._lookup_cache: dict[frozenset[tuple[str, str]], MappingGraph] = {}
        self._cache_version: str | None = None

    async def initialize(self) -> None:
        """Initialize and immediately sync the local database."""
        try:
            await self.sync_db()
        except Exception as exc:
            log.error(f"Failed to sync database: {exc}", exc_info=True)
            raise

    async def close(self) -> None:
        """Close the underlying mappings client session."""
        await self.mappings_client.close()

    async def __aenter__(self):
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager and close resources."""
        await self.close()

    def _sync_provenance_rows(
        self, session: Session, desired: dict[int, list[str]]
    ) -> None:
        """Ensure provenance rows align with the desired mapping sources."""
        mapping_ids = list(desired.keys())
        if not mapping_ids:
            return

        existing: dict[int, list[str]] = {}
        for chunk in batched(mapping_ids, self._SQLITE_SAFE_VARIABLES, strict=False):
            rows = (
                session.execute(
                    select(AnimapProvenance)
                    .where(AnimapProvenance.mapping_id.in_(chunk))
                    .order_by(AnimapProvenance.mapping_id, AnimapProvenance.n)
                )
                .scalars()
                .all()
            )
            for row in rows:
                existing.setdefault(row.mapping_id, []).append(row.source)

        ids_to_refresh: list[int] = []
        rows_to_insert: list[AnimapProvenance] = []

        for mapping_id, sources in desired.items():
            if sources != existing.get(mapping_id, []):
                ids_to_refresh.append(mapping_id)
                rows_to_insert.extend(
                    AnimapProvenance(mapping_id=mapping_id, n=i, source=source)
                    for i, source in enumerate(sources)
                )

        if not ids_to_refresh:
            return

        for chunk in batched(ids_to_refresh, self._SQLITE_SAFE_VARIABLES, strict=False):
            session.execute(
                delete(AnimapProvenance).where(AnimapProvenance.mapping_id.in_(chunk))
            )

        if rows_to_insert:
            session.add_all(rows_to_insert)

    def _build_edges(
        self,
        mappings: dict,
        provenance_by_descriptor: dict[str, list[str]],
    ) -> tuple[
        dict[str, MappingDescriptor],
        dict[tuple[str, str, str, str | None], AnimapEdge],
        dict[tuple[str, str, str, str | None], list[str]],
        int,
    ]:
        """Convert raw mappings into descriptor pairs and edges."""
        descriptors: dict[str, MappingDescriptor] = {}
        edges: dict[tuple[str, str, str, str | None], AnimapEdge] = {}
        provenance: dict[tuple[str, str, str, str | None], list[str]] = {}
        invalid_count = 0

        for raw_source, targets in mappings.items():
            try:
                source_desc = MappingDescriptor.parse(raw_source)
            except ValueError:
                log.warning("Invalid mapping descriptor $$'%s'$$; skipped", raw_source)
                invalid_count += 1
                continue

            descriptors[source_desc.key()] = source_desc

            if not isinstance(targets, dict):
                log.warning(
                    "Descriptor $$'%s'$$ has non-object target payload; skipped",
                    raw_source,
                )
                invalid_count += 1
                continue

            for raw_target, ranges in targets.items():
                try:
                    target_desc = MappingDescriptor.parse(raw_target)
                except ValueError:
                    log.warning(
                        "Invalid target descriptor $$'%s'$$ under $$'%s'$$; skipped",
                        raw_target,
                        raw_source,
                    )
                    invalid_count += 1
                    continue

                descriptors[target_desc.key()] = target_desc

                if not isinstance(ranges, dict):
                    log.warning(
                        "Descriptor $$'%s'$$ → $$'%s'$$ has non-object ranges; skipped",
                        raw_source,
                        raw_target,
                    )
                    invalid_count += 1
                    continue

                for source_range, destination_range in ranges.items():
                    if not isinstance(source_range, str) or not source_range:
                        invalid_count += 1
                        continue
                    if destination_range is not None and not isinstance(
                        destination_range, str
                    ):
                        invalid_count += 1
                        continue

                    key = (
                        source_desc.key(),
                        target_desc.key(),
                        source_range,
                        destination_range,
                    )
                    if key not in edges:
                        edges[key] = AnimapEdge(
                            source=source_desc,
                            destination=target_desc,
                            source_range=source_range,
                            destination_range=destination_range,
                        )
                    provenance.setdefault(key, []).extend(
                        provenance_by_descriptor.get(raw_source, [])
                    )

                    if destination_range is None:
                        continue

                    reverse_key = (
                        target_desc.key(),
                        source_desc.key(),
                        destination_range,
                        source_range,
                    )
                    if reverse_key not in edges:
                        edges[reverse_key] = AnimapEdge(
                            source=target_desc,
                            destination=source_desc,
                            source_range=destination_range,
                            destination_range=source_range,
                        )
                    provenance.setdefault(reverse_key, []).extend(
                        provenance_by_descriptor.get(raw_source, [])
                    )

        # Deduplicate provenance lists while preserving order
        for key, values in provenance.items():
            seen: set[str] = set()
            deduped: list[str] = []
            for value in values:
                if value in seen:
                    continue
                seen.add(value)
                deduped.append(value)
            provenance[key] = deduped

        return descriptors, edges, provenance, invalid_count

    def _build_cache_from_edges(
        self, edges: tuple[AnimapEdge, ...], version: str
    ) -> None:
        """Populate in-memory adjacency for fast lookups."""
        adjacency: dict[tuple[str, str], list[int]] = {}
        for idx, edge in enumerate(edges):
            for descriptor in (edge.source, edge.destination):
                adjacency.setdefault(
                    (descriptor.provider, descriptor.entry_id), []
                ).append(idx)

        self._edge_cache = edges
        self._adjacency = {key: tuple(ids) for key, ids in adjacency.items()}
        self._lookup_cache.clear()
        self._cache_version = version

    def _build_cache_from_db(self) -> None:
        """Rebuild the in-memory graph cache from the SQLite tables."""
        with db() as ctx:
            entries = {
                entry.id: entry
                for entry in ctx.session.execute(select(AnimapEntry)).scalars().all()
            }
            mappings = ctx.session.execute(select(AnimapMapping)).scalars().all()

        edges: list[AnimapEdge] = []

        for mapping in mappings:
            src_entry = entries.get(mapping.source_entry_id)
            dst_entry = entries.get(mapping.destination_entry_id)
            if not src_entry or not dst_entry:
                continue

            edges.append(
                AnimapEdge(
                    source=MappingDescriptor(
                        provider=src_entry.provider,
                        entry_id=src_entry.entry_id,
                        scope=src_entry.entry_scope,
                    ),
                    destination=MappingDescriptor(
                        provider=dst_entry.provider,
                        entry_id=dst_entry.entry_id,
                        scope=dst_entry.entry_scope,
                    ),
                    source_range=mapping.source_range,
                    destination_range=mapping.destination_range,
                )
            )

        self._build_cache_from_edges(tuple(edges), self._cache_version or "db")

    def _ensure_cache(self) -> None:
        if not self._edge_cache:
            self._build_cache_from_db()

    def get_graph_for_ids(self, external_ids: dict[str, str]) -> MappingGraph:
        """Return all edges touching the supplied external identifiers.

        Args:
            external_ids (dict[str, str]): Mapping of provider names to entry IDs.

        Returns:
            MappingGraph: Subgraph containing all relevant edges.
        """
        self._ensure_cache()

        if not external_ids:
            return MappingGraph(edges=tuple())

        cache_key = frozenset(external_ids.items())
        if self._cache_version is not None and cache_key in self._lookup_cache:
            return self._lookup_cache[cache_key]

        edge_indexes: set[int] = set()
        for provider, entry_id in external_ids.items():
            edge_indexes.update(self._adjacency.get((provider, entry_id), ()))

        if not edge_indexes:
            graph = MappingGraph(edges=tuple())
        else:
            graph = MappingGraph(edges=tuple(self._edge_cache[i] for i in edge_indexes))

        if self._cache_version is not None:
            self._lookup_cache[cache_key] = graph

        return graph

    async def sync_db(self) -> None:
        """Synchronize the local database with the upstream mappings."""
        self._edge_cache = tuple()
        self._adjacency = {}
        self._lookup_cache.clear()
        self._cache_version = None

        mappings = await self.mappings_client.load_mappings()
        provenance_by_descriptor = self.mappings_client.get_provenance()

        descriptors, edges, provenance, invalid_count = self._build_edges(
            mappings, provenance_by_descriptor
        )
        edge_list = tuple(edges.values())

        curr_mappings_hash = md5(
            json.dumps(mappings, sort_keys=True).encode()
        ).hexdigest()

        with db() as ctx:
            existing_entries = {
                f"{entry.provider}:{entry.entry_id}:{entry.entry_scope}": entry
                for entry in ctx.session.execute(select(AnimapEntry)).scalars().all()
            }

            new_entry_keys = set(descriptors.keys())
            existing_entry_keys = set(existing_entries.keys())

            to_delete_entries = existing_entry_keys - new_entry_keys
            to_insert_entries = new_entry_keys - existing_entry_keys

            if to_delete_entries:
                for chunk in batched(
                    [existing_entries[k].id for k in to_delete_entries],
                    self._SQLITE_SAFE_VARIABLES,
                    strict=False,
                ):
                    ctx.session.execute(
                        delete(AnimapEntry).where(AnimapEntry.id.in_(chunk))
                    )

            new_entries = [
                AnimapEntry(
                    provider=descriptors[key].provider,
                    entry_id=descriptors[key].entry_id,
                    entry_scope=descriptors[key].scope,
                )
                for key in to_insert_entries
            ]
            if new_entries:
                ctx.session.add_all(new_entries)
                ctx.session.flush()

            # Refresh entry map after inserts
            existing_entries = {
                f"{entry.provider}:{entry.entry_id}:{entry.entry_scope}": entry
                for entry in ctx.session.execute(select(AnimapEntry)).scalars().all()
            }

            # Translate edge keys to entry-id keyed tuples
            edge_key_to_ids: dict[tuple[int, int, str, str | None], AnimapEdge] = {}
            provenance_by_id_key: dict[tuple[int, int, str, str | None], list[str]] = {}
            for key, edge in edges.items():
                src_key, dst_key, source_range, destination_range = key
                src_entry = existing_entries.get(src_key)
                dst_entry = existing_entries.get(dst_key)
                if not src_entry or not dst_entry:
                    continue
                id_key = (src_entry.id, dst_entry.id, source_range, destination_range)
                edge_key_to_ids[id_key] = edge
                provenance_by_id_key[id_key] = provenance.get(key, [])

            existing_mappings: dict[tuple[int, int, str, str | None], AnimapMapping] = {
                (
                    mapping.source_entry_id,
                    mapping.destination_entry_id,
                    mapping.source_range,
                    mapping.destination_range,
                ): mapping
                for mapping in ctx.session.execute(select(AnimapMapping))
                .scalars()
                .all()
            }

            new_keys = set(edge_key_to_ids.keys())
            existing_keys = set(existing_mappings.keys())

            to_delete_mappings = existing_keys - new_keys
            to_insert_mappings = new_keys - existing_keys

            if to_delete_mappings:
                for chunk in batched(
                    list(to_delete_mappings),
                    self._SQLITE_SAFE_VARIABLES,
                    strict=False,
                ):
                    ctx.session.execute(
                        delete(AnimapMapping).where(
                            tuple_(
                                AnimapMapping.source_entry_id,
                                AnimapMapping.destination_entry_id,
                                AnimapMapping.source_range,
                                AnimapMapping.destination_range,
                            ).in_(chunk)
                        )
                    )

            new_mapping_rows = [
                AnimapMapping(
                    source_entry_id=key[0],
                    destination_entry_id=key[1],
                    source_range=key[2],
                    destination_range=key[3],
                )
                for key in to_insert_mappings
            ]
            if new_mapping_rows:
                ctx.session.add_all(new_mapping_rows)
                ctx.session.flush()

            # Refresh mapping map to include newly inserted rows (ids now populated)
            existing_mappings = {
                (
                    mapping.source_entry_id,
                    mapping.destination_entry_id,
                    mapping.source_range,
                    mapping.destination_range,
                ): mapping
                for mapping in ctx.session.execute(select(AnimapMapping))
                .scalars()
                .all()
            }

            desired_provenance: dict[int, list[str]] = {}
            for key, sources in provenance_by_id_key.items():
                mapping = existing_mappings.get(key)
                if mapping:
                    desired_provenance[mapping.id] = sources

            self._sync_provenance_rows(ctx.session, desired_provenance)

            ctx.session.merge(
                Housekeeping(key="animap_mappings_hash", value=curr_mappings_hash)
            )

            ctx.session.commit()

            self._build_cache_from_edges(edge_list, curr_mappings_hash)

            log.success(
                "Database sync complete: "
                f"{len(to_delete_entries)} entries removed, "
                f"{len(to_delete_mappings)} mappings removed, "
                f"{invalid_count} invalid, "
                f"{len(to_insert_entries)} inserted"
            )
