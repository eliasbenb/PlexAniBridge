from time import sleep
from typing import Optional, Union

import requests

from src import log
from src.models.anilist import (
    AniListFuzzyDate,
    AniListMedia,
    AniListMediaList,
    AniListMediaStatus,
    AniListMediaWithRelations,
)
from src.utils.rate_limitter import RateLimiter


class AniListClient:
    API_URL = "https://graphql.anilist.co"

    def __init__(self, anilist_token: str, dry_run: bool):
        self.anilist_token = anilist_token
        self.dry_run = dry_run

        self.rate_limiter = RateLimiter(self.__class__.__name__, requests_per_minute=90)
        self.anilist_user = self.__get_user()

    def __make_request(self, query: str, variables: Optional[dict] = None) -> dict:
        self.rate_limiter.wait_if_needed()

        response = requests.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.anilist_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"query": query, "variables": variables or {}},
        )

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            log.warning(
                f"{self.__class__.__name__}: Rate limit exceeded, waiting {retry_after} seconds"
            )
            sleep(retry_after + 1)
            return self.__make_request(query, variables)

        response.raise_for_status()
        return response.json()

    def __get_user(self) -> str:
        query = """
        query {
            Viewer {
                id
                name
            }
        }
        """

        response = self.__make_request(query)
        return response["data"]["Viewer"]["name"]

    def update_anime_entry(
        self,
        media_id: int,
        status: Optional[AniListMediaStatus] = None,
        score: Optional[float] = None,
        progress: Optional[int] = None,
        repeat: Optional[int] = None,
        notes: Optional[str] = None,
        start_date: Optional[AniListFuzzyDate] = None,
        end_date: Optional[AniListFuzzyDate] = None,
    ) -> dict:
        variables = {
            "mediaId": media_id,
            "status": status.value if status else None,
            "score": score,
            "progress": progress,
            "repeat": repeat,
            "notes": notes,
            "startedAt": start_date.model_dump() if start_date else None,
            "completedAt": end_date.model_dump() if end_date else None,
        }

        variables = {k: v for k, v in variables.items() if v is not None}

        log.debug(
            f"{self.__class__.__name__}: Updating anime entry {{media_id: {media_id}}} with variables: {variables}"
        )

        query = f"""
        mutation ($mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int, $repeat: Int, $notes: String, $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput) {{
            SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score, progress: $progress, repeat: $repeat, notes: $notes, startedAt: $startedAt, completedAt: $completedAt) {{
                {AniListMediaList.as_graphql()}
            }}
        }}
        """

        if self.dry_run:
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping list entry update for {{media_id: {media_id}}} with variables: {variables}"
            )
            return {}
        else:
            return self.__make_request(query, variables)["data"]["SaveMediaListEntry"]

    def search_anime(self, search_str: str, limit: int = 10) -> list[AniListMedia]:
        query = f"""
        query ($search: String, $limit: Int) {{
            Page(perPage: $limit) {{
                media(search: $search, type: ANIME) {{
                    {AniListMedia.as_graphql()}
                }}
            }}
        }}
        """

        log.debug(
            f"{self.__class__.__name__}: Searching for anime with query '{search_str}'"
        )

        response = self.__make_request(query, {"search": search_str, "limit": limit})
        return [AniListMedia(**media) for media in response["data"]["Page"]["media"]]

    def get_anime(
        self,
        anilist_id: Optional[int] = None,
        mal_id: Optional[int] = None,
        relations: Optional[bool] = False,
    ) -> Union[AniListMedia, AniListMediaWithRelations]:
        media_id = anilist_id or mal_id or None
        id_type = "id" if anilist_id else "idMal" if mal_id else None
        id_type_str = "anilist_id" if anilist_id else "mal_id" if mal_id else None

        if not media_id:
            raise ValueError("Either an AniList ID or a MAL ID must be provided")

        query = f"""
        query ($id: Int) {{
            Media({id_type}: $id, type: ANIME) {{
                {AniListMediaWithRelations.as_graphql() if relations else AniListMedia.as_graphql()}
            }}
        }}
        """

        log.debug(
            f"{self.__class__.__name__}: Getting anime data from AniList {{{id_type_str}: {media_id}}}"
        )

        response = self.__make_request(query, {id_type: media_id})
        if relations:
            return AniListMediaWithRelations(**response["data"]["Media"])
        else:
            return AniListMedia(**response["data"]["Media"])
