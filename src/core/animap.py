import json
from hashlib import md5
from pathlib import Path
from typing import Any

import requests
from pydantic import ValidationError
from sqlmodel import Session, column, delete, exists, func, select
from sqlmodel.sql.expression import UnaryExpression, or_

from src import log
from src.database import db
from src.models.animap import AniMap
from src.models.housekeeping import Housekeeping


class AniMapClient:
    """Client for managing the AniMap database.

    This client manages a local SQLite database that maps anime IDs between different services
    (AniList, TVDB, IMDB, etc.). It handles synchronization with the mapping source and
    provides query capabilities for ID mapping lookups.

    The database is automatically synchronized on client initialization and maintains
    a hash of the CDN data to minimize unnecessary updates.

    Attributes:
        CDN_URL (str): URL to the mappings JSON file in the PlexAniBridge-Mappings repository on GitHub

    Database Schema:
        The client manages the following tables:
        - AniMap: Stores the ID mappings between services
        - Housekeeping: Stores metadata like the CDN hash for sync management

    Mapping Source:
        https://github.com/eliasbenb/PlexAniBridge-Mappings

    Note:
        The client maintains data integrity by:
        - Only syncing when CDN content has changed (verified via MD5 hash)
        - Properly handling multi-value fields (mal_id, imdb_id)
        - Removing entries that no longer exist in the CDN
        - Using database transactions for atomic updates
    """

    SCHEMA_VERSION = "v2"
    CDN_URL = f"https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/{SCHEMA_VERSION}/mappings.json"
    SCHEMA_URL = f"https://cdn.statically.io/gh/eliasbenb/PlexAniBridge-Mappings/{SCHEMA_VERSION}/mappings.schema.json"

    def __init__(self, data_path: Path) -> None:
        self.custom_mappings_path = data_path / "mappings.custom.json"
        try:
            self._sync_db()
        except Exception as e:
            log.error(f"{self.__class__.__name__}: Failed to sync database: {e}")

    def reinit(self) -> None:
        """Reinitializes the AniMap database.

        Drops all tables and reinitializes the database from scratch.
        """
        self._sync_db()

    def _sync_db(self) -> None:
        """Synchronizes the local database with the mapping source.

        Performs the following steps:
        1. Checks if the CDN data has changed by comparing MD5 hashes
        2. If unchanged, skips the sync to avoid unnecessary updates
        3. If changed:
            - Downloads the latest mapping data
            - Converts data to appropriate types (handling multi-value fields)
            - Updates the local database using merge operations
            - Removes entries that no longer exist in the CDN
            - Updates the stored CDN hash

        Raises:
            requests.HTTPError: If the CDN request fails
            SQLAlchemyError: If database operations fail

        Note:
            - Uses MD5 hashing to detect changes in CDN data
            - Handles multi-value fields (mal_id, imdb_id) by splitting comma-separated strings
            - Uses SQLModel merge operations to efficiently update existing records
            - Maintains data consistency using database transactions
        """

        def single_val_to_list(value: Any) -> list[int | str]:
            """Converts a single value to a list if not already a list.

            Args:
                value (Any): Value to convert

            Returns:
                list[int | str]: Converted value
            """
            if value is None:
                return None
            return [value] if not isinstance(value, list) else value

        with Session(db.engine) as session:
            # First check if the CDN or custom data have changed. If not, we can skip the sync
            last_custom_hash = session.get(Housekeeping, "animap_custom_hash")
            last_cdn_hash = session.get(Housekeeping, "animap_cdn_hash")

            response = requests.get(self.CDN_URL)
            response.raise_for_status()
            response_data: dict = response.json()
            response_data.pop("$schema", None)

            if self.custom_mappings_path.exists():
                with self.custom_mappings_path.open("r") as f:
                    try:
                        custom_data: dict[str, Any] = json.load(f)
                    except json.JSONDecodeError:
                        log.warning(
                            f"{self.__class__.__name__}: Invalid custom mappings file at "
                            f"$$'{self.custom_mappings_path}'$$"
                        )
                        custom_data = {}

                    animap_defaults = {field: None for field in AniMap.model_fields}

                    validated_count = 0
                    tmp_custom_data = custom_data.copy()
                    for anilist_id_str, entry in custom_data.items():
                        if anilist_id_str.startswith("$"):
                            continue

                        try:
                            AniMap.model_validate(
                                {
                                    **animap_defaults,
                                    "anilist_id": int(anilist_id_str),
                                    **entry,
                                }
                            )
                            validated_count += 1
                        except (ValueError, ValidationError) as e:
                            log.warning(
                                f"{self.__class__.__name__}: Found an invalid custom mapping entry "
                                f"$${{anilist_id: {anilist_id_str}}}$$: {e}"
                            )
                            tmp_custom_data.pop(anilist_id_str)
                    custom_data = tmp_custom_data

                    log.info(
                        f"{self.__class__.__name__}: Loading {validated_count} custom mapping entries "
                        f"from $$'{self.custom_mappings_path}'$$"
                    )
            else:
                with self.custom_mappings_path.open("w") as f:
                    json.dump({"$schema": self.SCHEMA_URL}, f, indent=2)
                custom_data = {}

            cdn_data: dict[str, Any] = response_data

            curr_custom_hash = md5(
                json.dumps(custom_data, sort_keys=True).encode()
            ).hexdigest()
            curr_cdn_hash = md5(response.content).hexdigest()

            if (last_cdn_hash and last_cdn_hash.value == curr_cdn_hash) and (
                last_custom_hash and last_custom_hash.value == curr_custom_hash
            ):
                log.debug(
                    f"{self.__class__.__name__}: Cache is still valid, skipping sync"
                )
                return

            log.debug(
                f"{self.__class__.__name__}: Anime mapping changes detected, syncing database"
            )

            # Overload the CDN data with custom data
            merged_data: dict[str, dict[str, Any]] = cdn_data.copy()
            for anilist_id_str, entry in custom_data.items():
                if anilist_id_str.startswith("$"):
                    continue
                if anilist_id_str in merged_data:
                    if merged_data[anilist_id_str] == entry:
                        log.warning(
                            f"{self.__class__.__name__}: Found an exact duplicate entry in your custom mappings "
                            f"$${{anilist_id: {anilist_id_str}}}$$"
                        )
                    elif any(
                        merged_data[anilist_id_str].get(attr) == entry.get(attr)
                        for attr in AniMap.model_fields
                        if attr in entry and attr in merged_data[anilist_id_str]
                    ):
                        log.debug(
                            f"{self.__class__.__name__}: Found a partial duplicate entry in your custom mappings "
                            f"$${{anilist_id: {anilist_id_str}}}$$"
                        )

                    merged_data[anilist_id_str].update(entry)
                else:
                    merged_data[anilist_id_str] = entry

            values = [
                {
                    "anilist_id": int(anilist_id_str),
                    **{
                        field: entry[field]
                        for field in AniMap.model_fields
                        if field in entry
                    },
                }
                for anilist_id_str, entry in merged_data.items()
            ]

            session.exec(
                delete(AniMap).where(
                    AniMap.anilist_id.not_in([d["anilist_id"] for d in values])
                )
            )

            for value in values:
                for attr in ("mal_id", "imdb_id", "tmdb_movie_id", "tmdb_show_id"):
                    if attr in value:
                        value[attr] = single_val_to_list(value[attr])
                session.merge(AniMap(**value))

            session.merge(
                Housekeeping(key="animap_custom_hash", value=curr_custom_hash)
            )
            session.merge(Housekeeping(key="animap_cdn_hash", value=curr_cdn_hash))
            session.commit()

            log.debug(f"{self.__class__.__name__}: Database sync complete")

    def get_mappings(
        self,
        imdb: str | None = None,
        tmdb: int | None = None,
        tvdb: int | None = None,
        season: int | None = None,
        is_movie: bool = True,
    ) -> list[AniMap]:
        """Retrieves anime ID mappings based on provided criteria.

        Performs a complex database query to find entries that match the given identifiers
        and metadata. The search logic differs between movies and TV shows.

        Args:
            imdb (str | None): IMDB ID to match (can be partial match within array)
            tmdb (int | None): TMDB ID to match (movies and TV shows)
            tvdb (int | None): TVDB ID to match (TV shows only)
            season (int | None): TVDB season number for exact matching (TV shows only)
            is_movie (bool): Whether the search is for a movie or TV show

        Returns:
            list[AniMap]: Matching entries sorted by:
                1. TVDB season (if applicable)
                2. TVDB episode offset (if applicable)
                3. AniList ID
                4. AniDB ID

        Note:
            Search Behavior:
            - Only returns entries that have an AniList ID
            - IMDB matching is partial (can match within array of IDs)
            - TMDB, TVDB, season, and epoffset require exact matches
            - TV show searches can include season and episode offset criteria
            - Results are deduplicated based on (anilist_id, tvdb_season, tvdb_epoffset)
        """
        if not imdb and not tmdb and not tvdb:
            return []

        def json_contains(field: str, value: Any) -> UnaryExpression:
            """Generates a JSON_CONTAINS function for the given field.

            Args:
                field (str): Field name to search in
                value (Any): Value to search for

            Returns:
                Any: JSON_CONTAINS function
            """
            return exists(
                select(1)
                .select_from(func.json_each(column(field)))
                .where(column("value") == value)
            )

        with Session(db.engine) as session:
            conditions = []
            if is_movie:
                if imdb:
                    conditions.append(json_contains("imdb_id", imdb))
                if tmdb:
                    conditions.append(json_contains("tmdb_movie_id", tmdb))
            else:
                if tmdb:
                    conditions.append(json_contains("tmdb_show_id", tmdb))
                if imdb:
                    conditions.append(json_contains("imdb_id", imdb))
                if tvdb:
                    conditions.append(AniMap.tvdb_id == tvdb)

            if not conditions:
                return []

            query = select(AniMap).where(or_(*conditions)).group_by(AniMap.anilist_id)
            return session.exec(query).all()
