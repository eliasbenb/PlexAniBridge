from hashlib import md5
from typing import Optional, Union

import requests
from sqlmodel import Session, delete, func, select
from sqlmodel.sql.expression import and_, or_

from src import log
from src.models.animap import AniMap
from src.models.housekeeping import Housekeeping

from .db import db


class AniMapClient:
    """Client for managing the AniMap database (Kometa's anime ID mapping)

    The AniMap database allows for mapping between AniList IDs and other sources, including TVDB and IMDB.
    This class is responsible for syncing the local database with the CDN source and querying the database.

    Mapping Source: https://github.com/Kometa-Team/Anime-IDs/
    """

    CDN_URL = "https://cdn.jsdelivr.net/gh/Kometa-Team/Anime-IDs@refs/heads/master/anime_ids.json"

    def __init__(self) -> None:
        self.__sync_db()

    def __sync_db(self) -> None:
        """Sync the local AniMap database with the CDN source"""
        with Session(db) as session:
            # First check if the CDN data has changed. If not, we can skip the sync
            last_cdn_hash = session.get(Housekeeping, "animap_cdn_hash")

            with requests.get(self.CDN_URL) as response:
                response.raise_for_status()
                cdn_data: dict[int, dict[str, Union[int, str]]] = response.json()
                curr_cdn_hash = md5(response.content).hexdigest()

            if last_cdn_hash is None or last_cdn_hash.value != curr_cdn_hash:
                log.debug(
                    f"{self.__class__.__name__}: Anime mapping changes detected from the CDN, syncing database now"
                )
            else:
                log.debug(
                    f"{self.__class__.__name__}: Cache is still valid, skipping sync"
                )
                return

            values = [
                {
                    "anidb_id": anidb_id,
                    **{key: data.get(key) for key in AniMap.__fields__.keys()},
                }
                for anidb_id, data in cdn_data.items()
            ]  # Convert the CDN data to a format that can be inserted into the database

            session.exec(
                delete(AniMap).where(
                    AniMap.anidb_id.not_in([d["anidb_id"] for d in values])
                )
            )  # Delete any mappings that are no longer in the CDN data

            for value in values:  # Insert or update the mappings
                if value.get("mal_id"):
                    value["mal_id"] = [
                        int(id) for id in str(value["mal_id"]).split(",")
                    ]
                if value.get("imdb_id"):
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
            tmdb (Optional[int], optional): The TMDB movie ir show ID to match. Defaults to None.
            tvdb (Optional[int], optional): The TVDB ID to match. Defaults to None.
            season (Optional[int], optional): The TVDB season number to match. Defaults to None.
            epoffset (Optional[int], optional): The TVDB episode offset to match. Defaults to None.

        Returns:
            list[AniMap]: The list of AniMap entries that match the criteria
        """
        with Session(db) as session:
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

            # There is an edge case of about ~120 entries where the entry does not map directly to an AniList ID and
            # is instead mapped to multiple MAL IDs. Handling this would vastly increase complexity and computation.
            # So, I'm simply ignoring those ~120 entries by forcing there to be a 1:1 mapping.
            query = select(AniMap).where(
                or_(
                    AniMap.anilist_id.is_not(None),
                    AniMap.mal_id.is_(None),
                    func.json_array_length(AniMap.mal_id) == 1,
                )
            )
            if any(v is not None for v in partial_matches.values()):
                query = query.where(
                    or_(*(op(v) for op, v in partial_matches.items() if v is not None))
                )
            if any(v is not None for v in exact_matches.values()):
                query = query.where(
                    and_(*(op(v) for op, v in exact_matches.items() if v is not None))
                )

            return session.exec(query).all()
