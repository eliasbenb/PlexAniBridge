from hashlib import md5
from typing import Optional, Union

import requests
from sqlmodel import Session, delete, select
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
                if "anilist_id" in value and value["anilist_id"]:
                    value["anilist_id"] = [
                        int(id) for id in str(value["anilist_id"]).split(",")
                    ]
                if "mal_id" in value and value["mal_id"]:
                    value["mal_id"] = [
                        int(id) for id in str(value["mal_id"]).split(",")
                    ]
                if "imdb_id" in value and value["imdb_id"]:
                    value["imdb_id"] = str(value["imdb_id"]).split(",")

                session.merge(AniMap(**value))

            session.merge(Housekeeping(key="animap_cdn_hash", value=curr_cdn_hash))

            session.commit()

        log.debug(f"{self.__class__.__name__}: Database sync complete")

    def get_mappings(
        self,
        imdb_id: Optional[str] = None,
        tmdb_movie_id: Optional[int] = None,
        tmdb_show_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        tvdb_season: Optional[int] = None,
        tvdb_epoffset: Optional[int] = None,
    ) -> list[AniMap]:
        """Get the AniMap entries that match the provided criteria

        Certain criteria are optional, and the function will return entries that match any of the provided criteria.
        The TVDB season and episode offset must be exact matches for an entry to be returned.

        Args:
            imdb_id (Optional[str], optional): The IMDB ID to match. Defaults to None.
            tmdb_movie_id (Optional[int], optional): The TMDB movie ID to match. Defaults to None.
            tmdb_show_id (Optional[int], optional): The TMDB show ID to match. Defaults to None.
            tvdb_id (Optional[int], optional): The TVDB ID to match. Defaults to None.
            tvdb_season (Optional[int], optional): The TVDB season number to match. Defaults to None.
            tvdb_epoffset (Optional[int], optional): The TVDB episode offset to match. Defaults to None.

        Returns:
            list[AniMap]: The list of AniMap entries that match the criteria
        """
        with Session(db) as session:
            matching_conditions = []  # Conditions that are optional for matching (or_ operator)
            if imdb_id is not None:
                # The IMDB ID is stored as a list in the database, so we need to use the 'contains' operator
                matching_conditions.append(AniMap.imdb_id.contains(imdb_id))
            if tmdb_movie_id is not None:
                matching_conditions.append(AniMap.tmdb_movie_id == tmdb_movie_id)
            if tmdb_show_id is not None:
                matching_conditions.append(AniMap.tmdb_show_id == tmdb_show_id)
            if tvdb_id is not None:
                matching_conditions.append(AniMap.tvdb_id == tvdb_id)

            ordering_conditions = []  # Conditions that are required for ordering (and_ operator)
            if tvdb_season is not None:
                ordering_conditions.append(AniMap.tvdb_season == tvdb_season)
            if tvdb_epoffset is not None:
                ordering_conditions.append(AniMap.tvdb_epoffset == tvdb_epoffset)

            query = select(AniMap).where(or_(*matching_conditions))
            if len(ordering_conditions) > 0:
                query = query.where(and_(*ordering_conditions))

            return session.exec(query).all()
