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
    """Client for interacting with the AniList GraphQL API"""

    API_URL = "https://graphql.anilist.co"

    def __init__(self, anilist_token: str, dry_run: bool) -> None:
        self.anilist_token = anilist_token
        self.dry_run = dry_run

        self.rate_limiter = RateLimiter(self.__class__.__name__, requests_per_minute=90)
        self.anilist_user = self.__get_user()

    def __make_request(self, query: str, variables: Optional[dict] = None) -> dict:
        """Makes a request to the AniList API

        All requests are rate limited to 90 requests per minute.

        Args:
            query (str): The GraphQL query
            variables (Optional[dict], optional): The variables for the query. Defaults to None.

        Returns:
            dict: The JSON response from the API

        Raises:
            requests.HTTPError: If the request fails
        """
        self.rate_limiter.wait_if_needed()  # Rate limit the requests

        response = requests.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.anilist_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"query": query, "variables": variables or {}},
        )

        if response.status_code == 429:  # Handle rate limit retries
            retry_after = int(response.headers.get("Retry-After", 60))
            log.warning(
                f"{self.__class__.__name__}: Rate limit exceeded, waiting {retry_after} seconds"
            )
            sleep(retry_after + 1)
            return self.__make_request(query, variables)

        response.raise_for_status()
        return response.json()

    def __get_user(self) -> str:
        """Gets the authenticated user's username

        Returns:
            str: The username associated with the AniList token
        """
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
        """Updates an anime entry on the authenticated user's list

        Args:
            media_id (int): The AniList ID of the anime
            status (Optional[AniListMediaStatus], optional): The status of the anime. Defaults to None.
            score (Optional[float], optional): The user's score for the anime. Defaults to None.
            progress (Optional[int], optional): The user's progress in the anime. Defaults to None.
            repeat (Optional[int], optional): The number of times the anime has been rewatched. Defaults to None.
            notes (Optional[str], optional): The user's notes for the anime. Defaults to None.
            start_date (Optional[AniListFuzzyDate], optional): The date the anime was started. Defaults to None.
            end_date (Optional[AniListFuzzyDate], optional): The date the anime was completed. Defaults to None.

        Returns:
            dict: The updated anime entry
        """
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

        # Remove None values
        variables = {k: v for k, v in variables.items() if v is not None}

        log.debug(
            f"{self.__class__.__name__}: Updating anime entry with variables: {variables}"
        )

        query = f"""
        mutation ($mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int, $repeat: Int, $notes: String, $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput) {{
            SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score, progress: $progress, repeat: $repeat, notes: $notes, startedAt: $startedAt, completedAt: $completedAt) {{
                {AniListMediaList.as_graphql()}
            }}
        }}
        """

        if self.dry_run:  # Skip the request, only log the variables
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping anime entry update with variables: {variables}"
            )
            return {}
        else:
            return self.__make_request(query, variables)["data"]["SaveMediaListEntry"]

    def search_anime(self, search_str: str, limit: int = 10) -> list[AniListMedia]:
        """Searches for anime on AniList

        Args:
            search_str (str): The search query
            limit (int, optional): The maximum number of results to return. Defaults to 10.

        Returns:
            list[AniListMedia]: The search results
        """
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
        """Gets anime data from AniList

        Either an AniList ID or a MAL ID must be provided. If both are provided, the AniList ID will be used.

        Args:
            anilist_id (Optional[int], optional): The AniList ID of the anime. Defaults to None.
            mal_id (Optional[int], optional): The MAL ID of the anime. Defaults to None.
            relations (Optional[bool], optional): Whether to include relations in the response. Defaults to False.

        Returns:
            Union[AniListMedia, AniListMediaWithRelations]: The AniList Media object
        """
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
