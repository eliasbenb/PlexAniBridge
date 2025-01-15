from hashlib import md5
from typing import Any

import requests
from sqlmodel import Session, column, delete, exists, func, select, true
from sqlmodel.sql.expression import and_, or_

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

    CDN_URL = "https://cdn.jsdelivr.net/gh/eliasbenb/PlexAniBridge-Mappings@main/mappings.json"

    def __init__(self) -> None:
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
            # First check if the CDN data has changed. If not, we can skip the sync
            last_cdn_hash = session.get(Housekeeping, "animap_cdn_hash")

            response = requests.get(self.CDN_URL)
            response.raise_for_status()
            response_data: dict = response.json()
            response_data.pop("$schema", None)

            cdn_data: dict[int, dict[str, Any]] = response_data
            curr_cdn_hash = md5(response.content).hexdigest()

            if last_cdn_hash and last_cdn_hash.value == curr_cdn_hash:
                log.debug(
                    f"{self.__class__.__name__}: Cache is still valid, skipping sync"
                )
                return

            log.debug(
                f"{self.__class__.__name__}: Anime mapping changes detected, syncing database"
            )

            values = [
                {
                    "anilist_id": anilist_id,
                    **{
                        field: data[field]
                        for field in AniMap.model_fields
                        if field in data
                    },
                }
                for anilist_id, data in cdn_data.items()
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

            session.merge(Housekeeping(key="animap_cdn_hash", value=curr_cdn_hash))
            session.commit()

            log.debug(f"{self.__class__.__name__}: Database sync complete")

    def get_mappings(
        self,
        imdb: str | None = None,
        tmdb: int | None = None,
        tvdb: int | None = None,
        season: int | None = None,
        epoffset: int | None = None,
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
            epoffset (int | None): TVDB episode offset for exact matching (TV shows only)
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

        def json_contains(field: str, value: Any) -> Any:
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
            partial_conditions = []
            exact_conditions = []

            if imdb:
                partial_conditions.append(json_contains("imdb_id", imdb))
            if tmdb:
                if is_movie:
                    partial_conditions.append(json_contains("tmdb_movie_id", tmdb))
                else:
                    partial_conditions.append(json_contains("tmdb_show_id", tmdb))
            if not is_movie and tvdb:
                partial_conditions.append(AniMap.tvdb_id == tvdb)

            if not is_movie:
                if season is not None:
                    exact_conditions.append(AniMap.tvdb_season == season)
                if epoffset is not None:
                    exact_conditions.append(AniMap.tvdb_epoffset == epoffset)

            # Base query with all conditions
            query = (
                select(AniMap)
                .where(AniMap.anilist_id.is_not(None))
                .where(or_(*partial_conditions) if partial_conditions else true())
                .where(and_(*exact_conditions) if exact_conditions else true())
            )

            # Deduplicate entries
            subquery = query.group_by(
                AniMap.anilist_id,
                AniMap.tvdb_season,
                AniMap.tvdb_epoffset,
            ).subquery()

            # Final query with ordering
            final_query = (
                select(AniMap)
                .join(subquery, AniMap.anidb_id == subquery.c.anidb_id)
                .order_by(
                    (AniMap.tvdb_season == -1).asc(),  # Ensure tvdb_season=-1 is last
                    AniMap.tvdb_season,
                    AniMap.tvdb_epoffset,
                    AniMap.anilist_id,
                    AniMap.anidb_id,
                )
            )

            return session.exec(final_query).all()
