from hashlib import md5
from typing import Optional, Union

import requests
from sqlmodel import Session, delete, func, select
from sqlmodel.sql.expression import and_, or_

from src import log
from src.database import db
from src.models.animap import AniMap
from src.models.housekeeping import Housekeeping


class AniMapClient:
    """Client for managing the AniMap database (Kometa's anime ID mapping)

    The AniMap database allows for mapping between AniList IDs and other sources, including TVDB and IMDB.
    This class is responsible for syncing the local database with the CDN source and querying the database.

    Mapping Source: https://github.com/Kometa-Team/Anime-IDs/
    """

    CDN_URL = "https://cdn.jsdelivr.net/gh/Kometa-Team/Anime-IDs@refs/heads/master/anime_ids.json"

    def __init__(self) -> None:
        self._sync_db()

    def _sync_db(self) -> None:
        """Sync the local AniMap database with the CDN source"""
        with Session(db.engine) as session:
            # First check if the CDN data has changed. If not, we can skip the sync
            last_cdn_hash = session.get(Housekeeping, "animap_cdn_hash")

            response = requests.get(self.CDN_URL)
            response.raise_for_status()

            cdn_data: dict[int, dict[str, Union[int, str]]] = response.json()
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
                    **{field: data.get(field) for field in AniMap.model_fields},
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
        imdb: Optional[str] = None,
        tmdb: Optional[int] = None,
        tvdb: Optional[int] = None,
        season: Optional[int] = None,
        epoffset: Optional[int] = None,
        is_movie: bool = True,
    ) -> list[AniMap]:
        """Get the AniMap entries that match the provided criteria

        Certain criteria are optional, and the function will return entries that match any of the provided criteria.
        The TVDB season and episode offset must be exact matches for an entry to be returned.

        Args:
            imdb (Optional[str], optional): The IMDB ID to match. Defaults to None.
            tmdb (Optional[int], optional): The TMDB movie or show ID to match. Defaults to None.
            tvdb (Optional[int], optional): The TVDB ID to match. Defaults to None.
            season (Optional[int], optional): The TVDB season number to match. Defaults to None.
            epoffset (Optional[int], optional): The TVDB episode offset to match. Defaults to None.

        Returns:
            list[AniMap]: The list of AniMap entries that match the criteria
        """
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
            # Add exact matches
            if any(v is not None for v in exact_matches.values()):
                query = query.where(
                    and_(*(op(v) for op, v in exact_matches.items() if v is not None))
                )

            # Make sure we only return unique entries
            query = query.distinct(
                AniMap.anilist_id,
                AniMap.tvdb_season,
                AniMap.tvdb_epoffset,
            ).order_by(
                AniMap.anilist_id,
                AniMap.tvdb_season,
                AniMap.tvdb_epoffset,
                AniMap.anidb_id,
            )

            return session.exec(query).all()
