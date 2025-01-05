from hashlib import md5
from typing import Any

import requests
from sqlmodel import Session, delete, select
from sqlmodel.sql.expression import and_, or_

from src import log
from src.database import db
from src.models.animap import AniMap
from src.models.housekeeping import Housekeeping


class AniMapClient:
    """Client for managing the AniMap database (Kometa's anime ID mapping).

    This client manages a local SQLite database that maps anime IDs between different services
    (AniList, TVDB, IMDB, etc.). It handles synchronization with Kometa's CDN source and
    provides query capabilities for ID mapping lookups.

    The database is automatically synchronized on client initialization and maintains
    a hash of the CDN data to minimize unnecessary updates.

    Attributes:
        CDN_URL (str): URL to Kometa's anime ID mapping JSON file

    Database Schema:
        The client manages the following tables:
        - AniMap: Stores the ID mappings between services
        - Housekeeping: Stores metadata like the CDN hash for sync management

    Mapping Source:
        https://github.com/Kometa-Team/Anime-IDs/

    Note:
        The client maintains data integrity by:
        - Only syncing when CDN content has changed (verified via MD5 hash)
        - Properly handling multi-value fields (mal_id, imdb_id)
        - Removing entries that no longer exist in the CDN
        - Using database transactions for atomic updates
    """

    CDN_URL = "https://cdn.jsdelivr.net/gh/Kometa-Team/Anime-IDs@refs/heads/master/anime_ids.json"

    def __init__(self) -> None:
        self._sync_db()

    def _sync_db(self) -> None:
        """Synchronizes the local database with the Kometa CDN source.

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
        with Session(db.engine) as session:
            # First check if the CDN data has changed. If not, we can skip the sync
            last_cdn_hash = session.get(Housekeeping, "animap_cdn_hash")

            response = requests.get(self.CDN_URL)
            response.raise_for_status()

            cdn_data: dict[int, dict[str, Any]] = response.json()
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
                    "anidb_id": anidb_id,
                    **{
                        field: data.get(field)
                        for field in AniMap.model_fields
                        if field != "anidb_id"
                    },
                }
                for anidb_id, data in cdn_data.items()
            ]

            session.exec(
                delete(AniMap).where(
                    AniMap.anidb_id.not_in([d["anidb_id"] for d in values])
                )
            )

            for value in values:
                if "mal_id" in value and value["mal_id"] is not None:
                    value["mal_id"] = [
                        int(id) for id in str(value["mal_id"]).split(",")
                    ]
                if "imdb_id" in value and value["imdb_id"] is not None:
                    value["imdb_id"] = str(value["imdb_id"]).split(",")

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

        with Session(db.engine) as session:
            partial_matches = {AniMap.imdb_id.contains: imdb}
            exact_matches = {}
            if is_movie:
                partial_matches |= {AniMap.tmdb_movie_id.__eq__: tmdb}
            else:
                partial_matches |= {
                    AniMap.tmdb_show_id.__eq__: tmdb,
                    AniMap.tvdb_id.__eq__: tvdb,
                }
                exact_matches |= {
                    AniMap.tvdb_season.__eq__: season,
                    AniMap.tvdb_epoffset.__eq__: epoffset,
                }

            # Base filters
            query = select(AniMap).where(AniMap.anilist_id.is_not(None))

            # Add partial matches
            if any(v is not None for v in partial_matches.values()):
                query = query.where(
                    or_(*(op(v) for op, v in partial_matches.items() if v is not None))
                )
            if any(v is not None for v in exact_matches.values()):
                query = query.where(
                    and_(*(op(v) for op, v in exact_matches.items() if v is not None))
                )

            # Make sure we only return unique entries
            query = query.group_by(
                AniMap.anilist_id,
                AniMap.tvdb_season,
                AniMap.tvdb_epoffset,
            ).subquery()
            query = (
                select(AniMap)
                .join(query, AniMap.anidb_id == query.c.anidb_id)
                .order_by(
                    AniMap.tvdb_season,
                    AniMap.tvdb_epoffset,
                    AniMap.anilist_id,
                    AniMap.anidb_id,
                )
            )

            return session.exec(query).all()
