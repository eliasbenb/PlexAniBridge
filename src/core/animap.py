"""AniMap Client."""

import json
from collections.abc import Iterator
from hashlib import md5
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, column, delete, exists, false, func, or_, select
from sqlalchemy.orm.base import Mapped
from sqlalchemy.sql.elements import BinaryExpression, ColumnElement

from src import log
from src.config.database import db
from src.core.mappings import MappingsClient
from src.models.animap import AniMap
from src.models.housekeeping import Housekeeping

__all__ = ["AniMapClient"]


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

    def __init__(self, data_path: Path) -> None:
        """Initializes the AniMapClient.

        Args:
            data_path (Path): Path to the data directory for storing mappings and cache
                              files.
        """
        self.mappings_client = MappingsClient(data_path)
        self.data_path = data_path

    async def initialize(self) -> None:
        """Initialize the client by syncing the database.

        This should be called after creating the client instance.

        Raises:
            Exception: If database synchronization fails during initialization.
        """
        try:
            await self._sync_db()
        except Exception as e:
            log.error(
                f"{self.__class__.__name__}: Failed to sync database: {e}",
                exc_info=True,
            )
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

    async def _sync_db(self) -> None:
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

        with db as ctx:
            last_mappings_hash = ctx.session.get(Housekeeping, "animap_mappings_hash")

            animap_defaults = {column.name: None for column in AniMap.__table__.columns}
            valid_count = 0
            invalid_count = 0

            mappings = await self.mappings_client.load_mappings()
            tmp_mappings = mappings.copy()

            for key, entry in tmp_mappings.items():
                try:
                    anilist_id = int(key)
                except ValueError:
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
                        f"{self.__class__.__name__}: Found an invalid mapping entry "
                        f"$${{anilist_id: {anilist_id}}}$$: {e}"
                    )
                    mappings.pop(key)
                    invalid_count += 1

            curr_mappings_hash = md5(
                json.dumps(mappings, sort_keys=True).encode()
            ).hexdigest()

            if last_mappings_hash and last_mappings_hash.value == curr_mappings_hash:
                log.debug(
                    f"{self.__class__.__name__}: Cache is still valid, skipping sync"
                )
                return

            log.debug(
                f"{self.__class__.__name__}: Anime mapping changes detected, syncing "
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
                processed_entry: dict[str, Any] = {
                    "anilist_id": anilist_id,
                }

                for column in AniMap.__table__.columns:
                    field_name = column.name
                    if field_name in entry:
                        processed_entry[field_name] = entry[field_name]

                for attr in ("mal_id", "imdb_id", "tmdb_movie_id", "tmdb_show_id"):
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
                log.debug(f"{self.__class__.__name__}: No database changes needed")
            else:
                log.debug(
                    f"{self.__class__.__name__}: Syncing database with upstream: "
                    f"{len(to_delete)} deletions, {len(to_insert)} insertions, "
                    f"{len(to_update)} updates"
                )

            if to_delete:
                ctx.session.execute(
                    delete(AniMap).where(AniMap.anilist_id.in_(to_delete))
                )

            if to_insert:
                new_entries = [
                    AniMap(**new_data[anilist_id]) for anilist_id in to_insert
                ]
                ctx.session.add_all(new_entries)

            if to_update:
                for entry in to_update:
                    ctx.session.merge(entry)

            ctx.session.merge(
                Housekeeping(key="animap_mappings_hash", value=curr_mappings_hash)
            )

            ctx.session.commit()

            log.debug(f"{self.__class__.__name__}: Database sync complete")

    def get_mappings(
        self,
        imdb: str | list[str] | None = None,
        tmdb: int | list[int] | None = None,
        tvdb: int | list[int] | None = None,
        season: int | None = None,
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
        if not imdb and not tmdb and not tvdb:
            return iter([])

        imdb_list = (
            [imdb] if isinstance(imdb, str) else imdb if isinstance(imdb, list) else []
        )
        tmdb_list = (
            [tmdb] if isinstance(tmdb, int) else tmdb if isinstance(tmdb, list) else []
        )
        tvdb_list = (
            [tvdb] if isinstance(tvdb, int) else tvdb if isinstance(tvdb, list) else []
        )

        def json_array_contains(
            field: Mapped, values: list[Any]
        ) -> ColumnElement[bool]:
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

            conditions = []
            for value in values:
                conditions.append(
                    exists(
                        select(1)
                        .select_from(func.json_each(field))
                        .where(column("value") == value)
                    )
                )
            return or_(*conditions)

        def json_dict_contains(field: Mapped, key: str) -> BinaryExpression:
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

        with db as ctx:
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
                    or_conditions.append(
                        json_array_contains(AniMap.tmdb_show_id, tmdb_list)
                    )

                if tvdb_list:
                    if len(tvdb_list) == 1:
                        or_conditions.append(AniMap.tvdb_id == tvdb_list[0])
                    else:
                        or_conditions.append(AniMap.tvdb_id.in_(tvdb_list))
                if season:
                    and_conditions.append(
                        json_dict_contains(AniMap.tvdb_mappings, f"s{season}")
                    )

            merged_conditions: list[ColumnElement[bool]] = []
            if or_conditions:
                merged_conditions.append(or_(*or_conditions))
            if and_conditions:
                merged_conditions.append(and_(*and_conditions))
            where_clause = and_(*merged_conditions)

            query = select(AniMap).where(where_clause)

            yield from ctx.session.execute(query).scalars()
