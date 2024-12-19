from functools import cache
from textwrap import dedent
from time import sleep
from typing import Optional, Union

import requests

from src import log
from src.models.anilist import (
    Media,
    MediaFormat,
    MediaList,
    MediaStatus,
    MediaWithRelations,
    User,
)
from src.utils.rate_limitter import RateLimiter


class AniListClient:
    """Client for interacting with the AniList GraphQL API"""

    API_URL = "https://graphql.anilist.co"

    def __init__(self, anilist_token: str, dry_run: bool) -> None:
        self.anilist_token = anilist_token
        self.dry_run = dry_run

        self.rate_limiter = RateLimiter(self.__class__.__name__, requests_per_minute=90)
        self.anilist_user = self.get_user()

    def get_user(self) -> User:
        """Gets the authenticated user's username

        Returns:
            str: The username associated with the AniList token
        """
        query = dedent("""
        query {
            Viewer {
                id
                name
            }
        }
        """)

        response = self._make_request(query)["data"]["Viewer"]
        return User(**response)

    def update_anime_entry(self, media_list_entry: MediaList) -> MediaList:
        """Updates an anime entry on the authenticated user's list

        Args:
            media_list_entry (MediaList): The media list entry with the updated values

        Returns:
            MediaList: The updated media list entry
        """
        variables = media_list_entry.model_dump_json()

        query = dedent(f"""
        mutation ($mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int, $repeat: Int, $notes: String, $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput) {{
            SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score, progress: $progress, repeat: $repeat, notes: $notes, startedAt: $startedAt, completedAt: $completedAt) {{
{MediaList.model_dump_graphql(indent_level=3)}
            }}
        }}
        """)

        if self.dry_run:  # Skip the request, only log the variables
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping anime entry update {{anilist_id: {media_list_entry.media_id}}}"
            )
            return MediaList(
                id=-1,
                media_id=media_list_entry.media_id,
                user_id=-media_list_entry.user_id,
            )

        response = self._make_request(query, variables)["data"]["SaveMediaListEntry"]
        return MediaList(**response)

    def delete_anime_entry(self, entry_id: int, media_id: int) -> bool:
        """Deletes an anime entry on the authenticated user's list

        Args:
            media_id (int): The AniList ID of the anime

        Returns:
            bool: True if the entry was deleted, False otherwise
        """
        variables = MediaList(
            id=entry_id, media_id=media_id, user_id=self.anilist_user.id
        ).model_dump()

        query = dedent("""
        mutation ($id: Int) {
            DeleteMediaListEntry(id: $id) {
                deleted
            }
        }
        """)

        if self.dry_run:
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping anime entry deletion {{anilist_id: {media_id}}}"
            )
            return False

        response = self._make_request(query, variables)["data"]["DeleteMediaListEntry"]
        return response["deleted"]

    @cache
    def search_anime(
        self,
        search_str: str,
        is_movie: bool,
        episodes: Optional[int] = None,
        limit: int = 10,
    ) -> list[Media]:
        """Searches for anime on AniList

        Args:
            search_str (str): The search query
            is_movie (bool): Whether the anime is a movie
            episodes (Optional[int], optional): The number of episodes in the anime. Defaults to None.
            limit (int, optional): The maximum number of results to return. Defaults to 10.

        Returns:
            list[Media]: The search results
        """
        query = dedent(f"""
            query ($search: String, $formats: [MediaFormat], $limit: Int) {{
                Page(perPage: $limit) {{
                    media(search: $search, type: ANIME, format_in: $formats) {{
{Media.model_dump_graphql(indent_level=4)}
                    }}
                }}
            }}
        """)

        formats = (
            [MediaFormat.MOVIE, MediaFormat.SPECIAL]
            if is_movie
            else [
                MediaFormat.TV,
                MediaFormat.TV_SHORT,
                MediaFormat.ONA,
                MediaFormat.OVA,
            ]
        )

        variables = {
            "search": search_str,
            "formats": formats,
            "limit": limit,
        }

        log.debug(
            f"{self.__class__.__name__}: Searching for anime {'movie' if is_movie else 'show'} "
            f"with title '{search_str}' that has {episodes or 'unknown'} episodes"
        )

        response = self._make_request(query, variables)
        return [
            Media(**media)
            for media in response["data"]["Page"]["media"]
            if media["status"] == MediaStatus.RELEASING
            or media["episodes"] == episodes
            or not episodes
        ]

    def get_anime(
        self,
        anilist_id: Optional[int] = None,
        mal_id: Optional[int] = None,
        relations: Optional[bool] = False,
    ) -> Union[Media, MediaWithRelations]:
        """Gets anime data from AniList

        Either an AniList ID or a MAL ID must be provided. If both are provided, the AniList ID will be used.

        Args:
            anilist_id (Optional[int], optional): The AniList ID of the anime. Defaults to None.
            mal_id (Optional[int], optional): The MAL ID of the anime. Defaults to None.
            relations (Optional[bool], optional): Whether to include relations in the response. Defaults to False.

        Returns:
            Union[Media, MediaWithRelations]: The AniList Media object
        """
        media_id = anilist_id or mal_id or None
        id_type = "id" if anilist_id else "idMal" if mal_id else None
        id_type_str = "anilist_id" if anilist_id else "mal_id" if mal_id else None

        if not media_id:
            raise ValueError("Either an AniList ID or a MAL ID must be provided")

        query = dedent(f"""
        query (${id_type}: Int) {{
            Media({id_type}: ${id_type}, type: ANIME) {{
{MediaWithRelations.model_dump_graphql(indent_level=3) if relations else Media.model_dump_graphql(indent_level=3)}
            }}
        }}
        """)

        log.debug(
            f"{self.__class__.__name__}: Getting AniList media object {{{id_type_str}: {media_id}}}"
        )

        response = self._make_request(query, {id_type: media_id})
        if relations:
            return MediaWithRelations(**response["data"]["Media"])
        else:
            return Media(**response["data"]["Media"])

    def _make_request(
        self, query: str, variables: Optional[Union[dict, str]] = None
    ) -> dict:
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
            return self._make_request(query, variables)

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            log.error(
                f"{self.__class__.__name__}: Failed to make request to AniList API:",
                exc_info=e,
            )
            log.error(f"\t\t{response.text}")
            raise e
        return response.json()
