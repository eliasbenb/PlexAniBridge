from time import sleep
from typing import Optional, Union

import requests

from src import log
from src.models.anilist import (
    AnilistMedia,
    AnilistMediaList,
    AnilistMediaStatus,
    AnilistMediaWithRelations,
)
from src.utils.rate_limitter import RateLimiter


class AniListClient:
    API_URL = "https://graphql.anilist.co"

    def __init__(self, anilist_token: str, anilist_user: str, dry_run: bool):
        self.anilist_token = anilist_token
        self.anilist_user = anilist_user
        self.dry_run = dry_run

        self.rate_limiter = RateLimiter(self.__class__.__name__, requests_per_minute=90)
        self.__validate_auth()

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
            sleep(retry_after)
            return self.__make_request(query, variables)

        response.raise_for_status()
        return response.json()

    def __validate_auth(self) -> None:
        query = """
        query {
            Viewer {
                id
                name
            }
        }
        """

        response = self.__make_request(query)
        viewer = response["data"]["Viewer"]

        if viewer["name"] != self.anilist_user:
            raise ValueError(
                f"Authenticated user '{viewer['name']}' does not match configured user '{self.anilist_user}'"
            )

    def update_anime_entry(
        self,
        media_id: int,
        status: Optional[AnilistMediaStatus] = None,
        score: Optional[float] = None,
        progress: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> dict:
        variables = {
            "mediaId": media_id,
            "status": status.value if status else None,
            "score": score,
            "progress": progress,
            "notes": notes,
        }

        variables = {k: v for k, v in variables.items() if v is not None}

        log.debug(
            f"{self.__class__.__name__}: Updating anime entry with variables: {variables}"
        )

        query = f"""
        mutation ($mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int, $notes: String) {{
            SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score, progress: $progress, notes: $notes) {{
                {AnilistMediaList.as_graphql()}
            }}
        }}
        """

        if self.dry_run:
            log.info(f"{self.__class__.__name__}: Dry run enabled, skipping request")
            return {}
        else:
            return self.__make_request(query, variables)["data"]["SaveMediaListEntry"]

    def search_anime(self, search_str: str, limit: int = 10) -> list[AnilistMedia]:
        query = f"""
        query ($search: String, $limit: Int) {{
            Page(perPage: $limit) {{
                media(search: $search, type: ANIME) {{
                    {AnilistMedia.as_graphql()}
                }}
            }}
        }}
        """

        log.debug(
            f"{self.__class__.__name__}: Searching for anime with query '{search_str}'"
        )

        response = self.__make_request(query, {"search": search_str, "limit": limit})
        return [AnilistMedia(**media) for media in response["data"]["Page"]["media"]]

    def get_anime(
        self,
        anilist_id: Optional[int] = None,
        mal_id: Optional[int] = None,
        relations: Optional[bool] = False,
    ) -> Union[AnilistMedia, AnilistMediaWithRelations]:
        if anilist_id is None and mal_id is None:
            raise ValueError("Either an AniList ID or a MAL ID must be provided")

        media_id = anilist_id or mal_id
        id_type = "id" if anilist_id else "idMal"

        query = f"""
        query ($id: Int) {{
            Media({id_type}: $id, type: ANIME) {{
                {AnilistMediaWithRelations.as_graphql() if relations else AnilistMedia.as_graphql()}
            }}
        }}
        """

        log.debug(f"{self.__class__.__name__}: Getting anime with ID '{media_id}'")

        response = self.__make_request(query, {"id": media_id})
        if relations:
            return AnilistMediaWithRelations(**response["data"]["Media"])
        else:
            return AnilistMedia(**response["data"]["Media"])
