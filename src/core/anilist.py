from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from textwrap import dedent
from time import sleep
from typing import Optional, Union

import requests

from src import log
from src.models.anilist import (
    Media,
    MediaFormat,
    MediaList,
    MediaListCollection,
    MediaStatus,
    MediaWithRelations,
    User,
)
from src.utils.rate_limitter import RateLimiter


class AniListClient:
    """Client for interacting with the AniList GraphQL API"""

    API_URL = "https://graphql.anilist.co"
    BACKUP_RETENTION_DAYS = 7

    def __init__(self, anilist_token: str, backup_dir: Path, dry_run: bool) -> None:
        self.anilist_token = anilist_token
        self.backup_dir = backup_dir
        self.dry_run = dry_run

        self.rate_limiter = RateLimiter(self.__class__.__name__, requests_per_minute=90)
        self.user = self.get_user()

    def get_user(self) -> User:
        """Gets the owner user of the AniList token

        Returns:
            User: The anilist user object
        """
        query = dedent(f"""
        query {{
            Viewer {{
{User.model_dump_graphql(indent_level=3)}
            }}
        }}
        """).strip()

        response = self._make_request(query)["data"]["Viewer"]
        return User(**response)

    def update_anime_entry(self, media_list_entry: MediaList) -> Optional[MediaList]:
        """Updates an anime entry on the authenticated user's list

        Args:
            media_list_entry (MediaList): The media list entry with the updated values

        Returns:
            Optional[MediaList]: The updated media list entry
        """
        query = dedent(f"""
        mutation ($mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int, $repeat: Int, $notes: String, $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput) {{
            SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score, progress: $progress, repeat: $repeat, notes: $notes, startedAt: $startedAt, completedAt: $completedAt) {{
{MediaList.model_dump_graphql(indent_level=3)}
            }}
        }}
        """).strip()

        if self.dry_run:  # Skip the request, only log the variables
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping anime entry update $${{anilist_id: {media_list_entry.media_id}}}$$"
            )
            None

        variables = media_list_entry.model_dump_json(exclude_none=True)

        response = self._make_request(query, variables)["data"]["SaveMediaListEntry"]
        return MediaList(**response)

    def delete_anime_entry(self, entry_id: int, media_id: int) -> bool:
        """Deletes an anime entry on the authenticated user's list

        Args:
            entry_id (int): The AniList ID of the list entry to delete
            media_id (int): The AniList ID of the anime

        Returns:
            bool: True if the entry was deleted, False otherwise
        """
        query = dedent("""
        mutation ($id: Int) {
            DeleteMediaListEntry(id: $id) {
                deleted
            }
        }
        """).strip()

        if self.dry_run:
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping anime entry deletion $${{anilist_id: {media_id}}}$$"
            )
            return False

        variables = MediaList(
            id=entry_id, media_id=media_id, user_id=self.user.id
        ).model_dump_json(exclude_none=True)

        response = self._make_request(query, variables)["data"]["DeleteMediaListEntry"]
        return response["deleted"]

    def search_anime(
        self,
        search_str: str,
        is_movie: bool,
        episodes: Optional[int] = None,
        limit: int = 10,
    ) -> list[Media]:
        """Searches for anime on AniList

        This function is a wrapper of the cached `_search_anime()` it handles filtering while `_search_anime()`
        actually makes and caches the request.

        Args:
            search_str (str): The search query
            is_movie (bool): Whether the anime is a movie
            episodes (Optional[int], optional): The number of episodes in the anime. Defaults to None.
            limit (int, optional): The maximum number of results to return. Defaults to 10.

        Returns:
            list[Media]: The filtered search results
        """
        log.debug(
            f"{self.__class__.__name__}: Searching for anime {'movie' if is_movie else 'show'} "
            f"with title $$'{search_str}'$$ that has {episodes or 'unknown'} episodes"
        )

        res = self._search_anime(search_str, is_movie, limit)
        return [
            m
            for m in res
            if m.status == MediaStatus.RELEASING
            or m.episodes == episodes
            or not episodes
        ]

    @cache
    def _search_anime(
        self,
        search_str: str,
        is_movie: bool,
        limit: int = 10,
    ) -> list[Media]:
        """Helper function to `search_anime()` that caches AniList GraphQL results

        Args:
            search_str (str): The search query
            is_movie (bool): Whether the anime is a movie
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
        """).strip()

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

        response = self._make_request(query, variables)
        return [Media(**m) for m in response["data"]["Page"]["media"]]

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
        """).strip()

        log.debug(
            f"{self.__class__.__name__}: Getting AniList media object $${{{id_type_str}: {media_id}}}$$"
        )

        response = self._make_request(query, {id_type: media_id})

        if relations:
            return MediaWithRelations(**response["data"]["Media"])
        return Media(**response["data"]["Media"])

    def backup_anilist(self) -> None:
        query = dedent(f"""
        query MediaListCollection($userId: Int, $type: MediaType, $chunk: Int) {{
            MediaListCollection(userId: $userId, type: $type, chunk: $chunk) {{
{MediaListCollection.model_dump_graphql(indent_level=3)}
            }}
        }}
        """).strip()

        data = MediaListCollection(user=self.user, has_next_chunk=True)
        variables = {"userId": self.user.id, "type": "ANIME", "chunk": 0}

        while data.has_next_chunk:
            response = self._make_request(query, variables)["data"][
                "MediaListCollection"
            ]
            new_data = MediaListCollection(**response)

            data.has_next_chunk = new_data.has_next_chunk
            data.lists.extend(new_data.lists)

            variables["chunk"] += 1

        n = 1
        backup_file = self.backup_dir / f"plexanibridge-{self.user.name}.{n}.json"
        while backup_file.exists():
            n += 1
            backup_file = self.backup_dir / f"plexanibridge-{self.user.name}.{n}.json"

        if not backup_file.parent.exists():
            backup_file.parent.mkdir(parents=True)

        backup_file.write_text(data.model_dump_json(indent=2))
        log.info(f"{self.__class__.__name__}: Exported AniList data to '{backup_file}'")

        cutoff_date = datetime.now() - timedelta(days=self.BACKUP_RETENTION_DAYS)

        for file in self.backup_dir.glob("plexanibridge-*.json"):
            file_mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if file_mtime < cutoff_date:
                file.unlink()
                log.debug(f"{self.__class__.__name__}: Deleted old backup '{file}'")

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
