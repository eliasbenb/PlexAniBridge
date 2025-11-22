"""AniMap Client."""

import json
from collections.abc import Iterable, Iterator
from hashlib import md5
from itertools import batched
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from sqlalchemy.sql import and_, delete, or_, select

from src import log
from src.config.database import db
from src.core.mappings import MappingsClient
from src.models.db.animap import AniMap
from src.models.db.housekeeping import Housekeeping
from src.models.db.provenance import AniMapProvenance
from src.utils.sql import json_array_contains

__all__ = ["AniMapClient"]


if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.elements import ColumnElement


class AniMapClient:
    """Client for managing the AniMap database.

    This client manages a local SQLite database that maps anime IDs between different
    services (AniList, TVDB, IMDB, etc.). It handles synchronization with the mapping
    source and provides query capabilities for ID mapping lookups.

    The database is automatically synchronized on client initialization and maintains
    a hash of the CDN data to minimize unnecessary updates.

    Mapping Source:
        https://github.com/eliasbenb/PlexAniBridge-Mappings
    """

    _SQLITE_SAFE_VARIABLES = 900

    def __init__(self, data_path: Path, upstream_url: str | None) -> None:
        """Initializes the AniMapClient.

        Args:
            data_path (Path): Path to the data directory for storing mappings and cache
                              files.
            upstream_url (str | None): URL to the upstream mappings source JSON or YAML
                                    file. If None, no upstream mappings will be used.
        """
        self.data_path = data_path
        self.upstream_url = upstream_url
        self.mappings_client = MappingsClient(data_path, upstream_url)

    async def initialize(self) -> None:
        """Initialize the client by syncing the database.

        This should be called after creating the client instance.

        Raises:
            Exception: If database synchronization fails during initialization.
        """
        try:
            await self.sync_db()
        except Exception as e:
            log.error(f"Failed to sync database: {e}", exc_info=True)
            raise

    async def close(self) -> None:
        """Close the mappings client."""
        await self.mappings_client.close()

    async def __aenter__(self):
        """Context manager enter method."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit method.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Traceback object if an exception occurred.
        """
        await self.close()

    def _sync_provenance_rows(
        self,
        session: Session,
        provenance_map: dict[int, list[str]],
        anilist_ids: Iterable[int],
    ) -> None:
        """Ensure provenance rows match the sources observed during load."""
        target_ids = [
            anilist_id for anilist_id in anilist_ids if anilist_id in provenance_map
        ]

        if not target_ids:
            return

        existing: dict[int, list[str]] = {}
        for chunk in batched(target_ids, self._SQLITE_SAFE_VARIABLES, strict=False):
            rows = (
                session.execute(
                    select(AniMapProvenance)
                    .where(AniMapProvenance.anilist_id.in_(chunk))
                    .order_by(AniMapProvenance.anilist_id, AniMapProvenance.n)
                )
                .scalars()
                .all()
            )
            for row in rows:
                existing.setdefault(row.anilist_id, []).append(row.source)

        ids_to_refresh: list[int] = []
        rows_to_insert: list[AniMapProvenance] = []

        for anilist_id in target_ids:
            desired = provenance_map.get(anilist_id, [])
            if desired != existing.get(anilist_id, []):
                ids_to_refresh.append(anilist_id)
                rows_to_insert.extend(
                    AniMapProvenance(anilist_id=anilist_id, n=i, source=source)
                    for i, source in enumerate(desired)
                )

        if not ids_to_refresh:
            return

        for chunk in batched(ids_to_refresh, self._SQLITE_SAFE_VARIABLES, strict=False):
            session.execute(
                delete(AniMapProvenance).where(AniMapProvenance.anilist_id.in_(chunk))
            )

        if rows_to_insert:
            session.add_all(rows_to_insert)

    def _entries_are_equal(self, existing_entry: AniMap, new_entry: AniMap) -> bool:
        """Compare two AniMap entries for equality.

        Args:
            existing_entry (AniMap): Existing database entry
            new_entry (AniMap): New entry to compare

        Returns:
            bool: True if entries are equal, False otherwise
        """
        for column_attr in AniMap.__table__.columns:
            field_name = column_attr.name
            existing_value = getattr(existing_entry, field_name)
            new_value = getattr(new_entry, field_name)
            if existing_value != new_value:
                return False
        return True

    async def sync_db(self) -> None:
        """Synchronizes the local database with the mapping source."""

        def single_val_to_list(value: Any) -> list[Any] | None:
            """Converts a single value to a list if not already a list.

            Args:
                value (Any): Value to convert

            Returns:
                list[int | str]: Converted value
            """
            if value is None:
                return None
            return [value] if not isinstance(value, list) else value

        with db() as ctx:
            last_mappings_hash = ctx.session.get(Housekeeping, "animap_mappings_hash")

            animap_defaults = {column.name: None for column in AniMap.__table__.columns}
            valid_count = 0
            invalid_count = 0

            mappings = await self.mappings_client.load_mappings()
            provenance_map = self.mappings_client.get_provenance()
            tmp_mappings = mappings.copy()

            for key, entry in tmp_mappings.items():
                try:
                    anilist_id = int(key)
                except ValueError:
                    invalid_count += 1
                    continue

                if entry is None:
                    # Null override entries clear all fields for the given AniList ID
                    mappings[key] = {}
                    valid_count += 1
                    continue

                if not isinstance(entry, dict):
                    log.warning(
                        "Found an invalid mapping entry "
                        f"$${{anilist_id: {anilist_id}}}$$: expected an object"
                    )
                    mappings.pop(key)
                    invalid_count += 1
                    continue

                try:
                    AniMap(
                        **{
                            **animap_defaults,
                            "anilist_id": anilist_id,
                            **entry,
                        }
                    )
                    valid_count += 1
                except (ValueError, ValidationError, TypeError) as e:
                    log.warning(
                        f"Found an invalid mapping entry "
                        f"$${{anilist_id: {anilist_id}}}$$: {e}"
                    )
                    mappings.pop(key)
                    invalid_count += 1

            curr_mappings_hash = md5(
                json.dumps(mappings, sort_keys=True).encode()
            ).hexdigest()

            if last_mappings_hash and last_mappings_hash.value == curr_mappings_hash:
                log.debug(
                    "Cache is still valid, refreshing provenance and skipping sync"
                )
                existing_ids = set(
                    ctx.session.execute(select(AniMap.anilist_id)).scalars().all()
                )
                provenance_scope = existing_ids & set(provenance_map.keys())
                self._sync_provenance_rows(
                    ctx.session, provenance_map, provenance_scope
                )
                if provenance_scope:
                    ctx.session.commit()
                return

            log.debug(
                f"Anime mapping changes detected, syncing "
                f"database.  Validated {valid_count} entries, removed {invalid_count} "
                f"invalid entries"
            )

            existing_entries_query = ctx.session.execute(select(AniMap))
            existing_entries = {
                entry.anilist_id: entry
                for entry in existing_entries_query.scalars().all()
            }

            new_data = {}
            for key, entry in mappings.items():
                anilist_id = int(key)
                # Start from the column defaults so omitted fields become None
                # and will overwrite existing DB values on update
                processed_entry: dict[str, Any] = {
                    **animap_defaults,
                    "anilist_id": anilist_id,
                }

                for column in AniMap.__table__.columns:
                    field_name = column.name
                    if field_name in entry:
                        processed_entry[field_name] = entry[field_name]

                for attr in ("mal_id", "imdb_id", "tmdb_movie_id"):
                    if attr in processed_entry:
                        processed_entry[attr] = single_val_to_list(
                            processed_entry[attr]
                        )

                new_data[anilist_id] = processed_entry

            existing_ids = set(existing_entries.keys())
            new_ids = set(new_data.keys())

            to_delete = existing_ids - new_ids
            to_insert = new_ids - existing_ids
            to_check_update = existing_ids & new_ids

            to_update = []
            for anilist_id in to_check_update:
                existing_entry = existing_entries[anilist_id]
                new_entry_data = new_data[anilist_id]
                new_entry = AniMap(**new_entry_data)

                if not self._entries_are_equal(existing_entry, new_entry):
                    to_update.append(new_entry)

            operations_count = len(to_delete) + len(to_insert) + len(to_update)

            if operations_count == 0:
                log.debug("No database changes needed")
            else:
                log.debug(
                    f"Syncing database with upstream: "
                    f"{len(to_delete)} deletions, {len(to_insert)} insertions, "
                    f"{len(to_update)} updates"
                )

            if to_delete:
                for chunk in batched(
                    to_delete, self._SQLITE_SAFE_VARIABLES, strict=False
                ):
                    ctx.session.execute(
                        delete(AniMap).where(AniMap.anilist_id.in_(chunk))
                    )

            if to_insert:
                new_entries = [
                    AniMap(**new_data[anilist_id]) for anilist_id in to_insert
                ]
                ctx.session.add_all(new_entries)

            if to_update:
                for entry in to_update:
                    ctx.session.merge(entry)

            provenance_scope = new_ids & set(provenance_map.keys())
            self._sync_provenance_rows(ctx.session, provenance_map, provenance_scope)

            ctx.session.merge(
                Housekeeping(key="animap_mappings_hash", value=curr_mappings_hash)
            )

            ctx.session.commit()

            log.debug("Database sync complete")

    def get_mappings(
        self,
        imdb: str | list[str] | None = None,
        tmdb: int | list[int] | None = None,
        tvdb: int | list[int] | None = None,
        is_movie: bool = True,
    ) -> Iterator[AniMap]:
        """Retrieve anime ID mappings based on provided criteria.

        Performs a complex database query to find entries that match the given
        identifiers and metadata. The search logic differs between movies and TV
        shows, with movies using IMDB/TMDB and shows using TVDB with optional
        season filtering.

        Args:
            imdb: IMDB ID(s) to match. Can be partial match within array.
            tmdb: TMDB ID(s) to match for movies and TV shows.
            tvdb: TVDB ID(s) to match for TV shows only.
            season: TVDB season number for exact matching on TV shows only.
            is_movie: Whether the search is for a movie or TV show.

        Yields:
            Matching anime mapping entries.
        """
        log.debug(
            f"Querying mappings with imdb={imdb}, "
            f"tmdb={tmdb}, tvdb={tvdb}, is_movie={is_movie}"
        )

        if not imdb and not tmdb and not tvdb:
            yield from ()

        imdb_list = (
            [imdb] if isinstance(imdb, str) else imdb if isinstance(imdb, list) else []
        )
        tmdb_list = (
            [tmdb] if isinstance(tmdb, int) else tmdb if isinstance(tmdb, list) else []
        )
        tvdb_list = (
            [tvdb] if isinstance(tvdb, int) else tvdb if isinstance(tvdb, list) else []
        )

        with db() as ctx:
            or_conditions = []
            and_conditions = []

            if is_movie:
                if imdb_list:
                    or_conditions.append(json_array_contains(AniMap.imdb_id, imdb_list))
                if tmdb_list:
                    or_conditions.append(
                        json_array_contains(AniMap.tmdb_movie_id, tmdb_list)
                    )
            else:
                if imdb_list:
                    or_conditions.append(json_array_contains(AniMap.imdb_id, imdb_list))
                if tmdb_list:
                    if len(tmdb_list) == 1:
                        or_conditions.append(AniMap.tmdb_show_id == tmdb_list[0])
                    else:
                        or_conditions.append(AniMap.tmdb_show_id.in_(tmdb_list))
                if tvdb_list:
                    if len(tvdb_list) == 1:
                        or_conditions.append(AniMap.tvdb_id == tvdb_list[0])
                    else:
                        or_conditions.append(AniMap.tvdb_id.in_(tvdb_list))

            merged_conditions: list[ColumnElement[bool]] = []
            if or_conditions:
                merged_conditions.append(or_(*or_conditions))
            if and_conditions:
                merged_conditions.append(and_(*and_conditions))
            where_clause = and_(*merged_conditions)

            query = select(AniMap).where(where_clause)

            yield from ctx.session.execute(query).scalars()
