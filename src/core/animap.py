import json
from hashlib import md5
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlmodel import (
    Session,
    and_,
    column,
    delete,
    exists,
    func,
    or_,
    select,
    true,
)
from sqlmodel.sql.expression import InstrumentedAttribute, UnaryExpression

from src import log
from src.core.mappings import MappingsClient
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

    Mapping Source:
        https://github.com/eliasbenb/PlexAniBridge-Mappings
    """

    SCHEMA_VERSION = "v2"
    CDN_URL = f"https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/{SCHEMA_VERSION}/mappings.json"
    SCHEMA_URL = f"https://cdn.statically.io/gh/eliasbenb/PlexAniBridge-Mappings/{SCHEMA_VERSION}/mappings.schema.json"

    MAPPING_FILES = [
        "mappings.custom.json",
        "mappings.custom.yaml",
        "mappings.custom.yml",
        "mappings.custom.toml",
    ]

    def __init__(self, data_path: Path) -> None:
        self.mappings_client = MappingsClient(data_path)
        self.data_path = data_path

        try:
            self._sync_db()
        except Exception as e:
            log.error(
                f"{self.__class__.__name__}: Failed to sync database: {e}",
                exc_info=True,
            )

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
            last_mappings_hash = session.get(Housekeeping, "animap_mappings_hash")

            animap_defaults = {field: None for field in AniMap.model_fields}
            validated_count = 0

            mappings = self.mappings_client.load_mappings()
            tmp_mappings = mappings.copy()

            for key, entry in tmp_mappings.items():
                try:
                    anilist_id = int(key)
                except ValueError:
                    continue

                try:
                    AniMap.model_validate(
                        {
                            **animap_defaults,
                            "anilist_id": anilist_id,
                            **entry,
                        }
                    )
                    validated_count += 1
                except (ValueError, ValidationError) as e:
                    log.warning(
                        f"{self.__class__.__name__}: Found an invalid mapping entry "
                        f"$${{anilist_id: {anilist_id}}}$$: {e}"
                    )
                    tmp_mappings.pop(key)
            mappings = tmp_mappings

            log.info(
                f"{self.__class__.__name__}: Loading {validated_count} mapping entries"
            )

            curr_mappings_hash = md5(
                json.dumps(mappings, sort_keys=True).encode()
            ).hexdigest()

            if last_mappings_hash and last_mappings_hash.value == curr_mappings_hash:
                log.debug(
                    f"{self.__class__.__name__}: Cache is still valid, skipping sync"
                )
                return

            log.debug(
                f"{self.__class__.__name__}: Anime mapping changes detected, syncing database"
            )

            values = [
                {
                    "anilist_id": int(key),
                    **{
                        field: entry[field]
                        for field in AniMap.model_fields
                        if field in entry
                    },
                }
                for key, entry in mappings.items()
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
                Housekeeping(key="animap_mappings_hash", value=curr_mappings_hash)
            )
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

        def json_array_contains(
            field: InstrumentedAttribute, value: Any
        ) -> UnaryExpression:
            """Generates a JSON_CONTAINS function for the given field.

            Args:
                field (InstrumentedAttribute): Field to search in
                value (Any): Value to search for

            Returns:
                UnaryExpression: JSON_CONTAINS function
            """
            return exists(
                select(1)
                .select_from(func.json_each(field))
                .where(column("value") == value)
            )

        def json_dict_contains(
            field: InstrumentedAttribute, key: str
        ) -> UnaryExpression:
            """Generate a SQL expression for checking if a JSON field contains a key.

            Args:
                field (InstrumentedAttribute): Field to search in
                key (str): Value to search for

            Returns:
                UnaryExpression: JSON_CONTAINS function
            """
            return func.json_type(field, f"$.{key}").is_not(None)

        with Session(db.engine) as session:
            or_conditions = []
            and_conditions = []

            if is_movie:
                if imdb:
                    or_conditions.append(json_array_contains(AniMap.imdb_id, imdb))
                if tmdb:
                    or_conditions.append(
                        json_array_contains(AniMap.tmdb_movie_id, tmdb)
                    )
            else:
                if imdb:
                    or_conditions.append(json_array_contains(AniMap.imdb_id, imdb))
                if tmdb:
                    or_conditions.append(json_array_contains(AniMap.tmdb_show_id, tmdb))
                if tvdb:
                    or_conditions.append(AniMap.tvdb_id == tvdb)
                if season:
                    and_conditions.append(
                        json_dict_contains(AniMap.tvdb_mappings, f"s{season}")
                    )

            final_conditions = true()
            if or_conditions:
                final_conditions = and_(final_conditions, or_(*or_conditions))
            if and_conditions:
                final_conditions = and_(final_conditions, *and_conditions)

            query = select(AniMap).where(final_conditions)
            return session.exec(query).all()
