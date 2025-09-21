"""AniList Client."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
from async_lru import alru_cache
from limiter import Limiter

from src import __version__, log
from src.exceptions import AniListTokenRequiredError
from src.models.schemas.anilist import (
    Media,
    MediaFormat,
    MediaList,
    MediaListCollection,
    MediaListCollectionWithMedia,
    MediaListGroup,
    MediaListWithMedia,
    MediaStatus,
    User,
)

__all__ = ["AniListClient"]

# The rate limit for the AniList API *should* be 90 requests per minute, but in practice
# it seems to be around 30 requests per minute
anilist_limiter = Limiter(rate=30 / 60, capacity=3, jitter=False)


class AniListClient:
    """Client for interacting with the AniList GraphQL API.

    This client provides methods to interact with the AniList GraphQL API, including
    searching for anime, updating user lists, and managing anime entries. It implements
    rate limiting and local caching to optimize API usage.
    """

    API_URL = "https://graphql.anilist.co"
    BACKUP_RETENTION_DAYS = 7

    def __init__(
        self,
        anilist_token: str | None,
        backup_dir: Path | None,
        dry_run: bool,
        profile_name: str | None,
    ) -> None:
        """Initialize the AniList client.

        Args:
            anilist_token (str | None): Authentication token for AniList API; if None,
                client operates in public mode for read-only queries
            backup_dir (Path | None): Directory path where backup files will be stored
            dry_run (bool): If True, simulates API calls without making actual changes
            profile_name (str | None): Owning profile name; optional in public mode
        """
        self.anilist_token = anilist_token
        self.backup_dir = backup_dir
        self.dry_run = dry_run
        self.profile_name = profile_name or "public"
        self._session: aiohttp.ClientSession | None = None

        self.offline_anilist_entries: dict[int, Media] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session.

        Returns:
            aiohttp.ClientSession: The active session for making HTTP requests.
        """
        if self._session is None or self._session.closed:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"PlexAniBridge/{__version__}",
            }
            if self.anilist_token:
                headers["Authorization"] = f"Bearer {self.anilist_token}"

            self._session = aiohttp.ClientSession(headers=headers)

        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> AniListClient:
        """Async context manager entry.

        Returns:
            AniListClient: Self for use in async with statements.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        await self.close()

    async def initialize(self):
        """Initialize the client by getting user info and backing up data.

        In public (unauthenticated) mode, initialization is a no-op.
        """
        # If no token is provided, operate in public mode without user context
        if not self.anilist_token:
            self.offline_anilist_entries.clear()
            return

        self.user = await self.get_user()
        self.user_tz = self.get_user_tz()
        self.offline_anilist_entries.clear()
        await self.backup_anilist()

    def _ensure_authenticated(self) -> None:
        """Ensure that client has authentication for privileged operations."""
        if not self.anilist_token:
            raise AniListTokenRequiredError(
                "This operation requires an authenticated AniList client"
            )

    async def get_user(self) -> User:
        """Retrieves the authenticated user's information from AniList.

        Makes a GraphQL query to fetch detailed user information including ID, name,
        and other profile data for the authenticated user.

        Returns:
            User: Object containing the authenticated user's information

        Raises:
            aiohttp.ClientError: If the API request fails
        """
        query = f"""
        query {{
            Viewer {{
                {User.model_dump_graphql()}
            }}
        }}
        """

        response = await self._make_request(query)
        return User(**response["data"]["Viewer"])

    def get_user_tz(self) -> timezone:
        """Returns the authenticated user's timezone.

        Returns:
            timezone: The timezone of the authenticated user
        """
        try:
            if self.user.options and self.user.options.timezone:
                hours, minutes = map(int, self.user.options.timezone.split(":"))
            else:
                return UTC
            return timezone(timedelta(hours=hours, minutes=minutes))
        except (AttributeError, ValueError):
            return UTC

    async def update_anime_entry(self, media_list_entry: MediaList) -> None:
        """Updates an anime entry on the authenticated user's list.

        Sends a mutation to modify an existing anime entry in the user's list with new
        values for status, score, progress, etc.

        Args:
            media_list_entry (MediaList): Updated AniList entry to save

        Raises:
            aiohttp.ClientError: If the API request fails
        """
        self._ensure_authenticated()

        query = f"""
        mutation (
            $mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int,
            $repeat: Int, $notes: String, $startedAt: FuzzyDateInput,
            $completedAt: FuzzyDateInput
        ) {{
            SaveMediaListEntry(
                mediaId: $mediaId, status: $status, score: $score, progress: $progress,
                repeat: $repeat, notes: $notes, startedAt: $startedAt,
                completedAt: $completedAt
            ) {{
                {MediaListWithMedia.model_dump_graphql()}
            }}
        }}
        """

        if self.dry_run:  # Skip the request, only log the variables
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping anime entry "
                f"update $${{anilist_id: {media_list_entry.media_id}}}$$"
            )
            return None

        variables = media_list_entry.model_dump_json(exclude_none=True)

        response = await self._make_request(query, variables)
        save_response = response["data"]["SaveMediaListEntry"]

        self.offline_anilist_entries[media_list_entry.media_id] = (
            self._media_list_entry_to_media(MediaListWithMedia(**save_response))
        )

    async def batch_update_anime_entries(
        self, media_list_entries: list[MediaList]
    ) -> None:
        """Updates multiple anime entries on the authenticated user's list.

        Sends a batch mutation to modify multiple existing anime entries in the user's
        list. Processes entries in batches of 10 to avoid overwhelming the API.

        Args:
            media_list_entries (list[MediaList]): List of updated AniList entries to
                save.

        Raises:
            aiohttp.ClientError: If the API request fails.
        """
        self._ensure_authenticated()

        BATCH_SIZE = 10

        if not media_list_entries:
            return None

        for i in range(0, len(media_list_entries), BATCH_SIZE):
            batch = media_list_entries[i : i + BATCH_SIZE]
            log.debug(
                f"{self.__class__.__name__}: Updating batch of anime entries "
                f"$${{anilist_id: {[m.media_id for m in batch]}}}$$"
            )

            variable_declarations = []
            mutation_fields = []
            variables = {}

            for j, media_list_entry in enumerate(batch):
                variable_declarations.extend(
                    [
                        f"$mediaId{j}: Int",
                        f"$status{j}: MediaListStatus",
                        f"$score{j}: Float",
                        f"$progress{j}: Int",
                        f"$repeat{j}: Int",
                        f"$notes{j}: String",
                        f"$startedAt{j}: FuzzyDateInput",
                        f"$completedAt{j}: FuzzyDateInput",
                    ]
                )
                mutation_field = f"""
                    m{j}: SaveMediaListEntry(
                        mediaId: $mediaId{j},
                        status: $status{j},
                        score: $score{j},
                        progress: $progress{j},
                        repeat: $repeat{j},
                        notes: $notes{j},  
                        startedAt: $startedAt{j},
                        completedAt: $completedAt{j}
                    ) {{
                        {MediaListWithMedia.model_dump_graphql()}
                    }}
                """
                mutation_fields.append(mutation_field)

                entry_vars: dict = json.loads(
                    media_list_entry.model_dump_json(exclude_none=True)
                )
                for k, v in entry_vars.items():
                    variables[f"{k}{j}"] = v

            nl = "\n"
            query = f"""
                mutation BatchUpdateEntries({", ".join(variable_declarations)}) {{
                    {nl.join(mutation_fields)}
                }}
            """

            if self.dry_run:
                log.info(
                    f"{self.__class__.__name__}: Dry run enabled, skipping anime entry "
                    f"update $${{anilist_id: {[m.media_id for m in batch]}}}$$"
                )
                continue

            response: dict[str, dict[str, dict]] = await self._make_request(
                query, json.dumps(variables)
            )

            for mutation_data in response["data"].values():
                if "mediaId" not in mutation_data:
                    continue
                self.offline_anilist_entries[mutation_data["mediaId"]] = (
                    self._media_list_entry_to_media(MediaListWithMedia(**mutation_data))
                )

    async def delete_anime_entry(self, entry_id: int, media_id: int) -> bool:
        """Deletes an anime entry from the authenticated user's list.

        Sends a mutation to remove a specific anime entry from the user's list.

        Args:
            entry_id (int): The AniList ID of the list entry to delete.
            media_id (int): The AniList ID of the anime being deleted.

        Returns:
            bool: True if the entry was successfully deleted and not in dry run mode,
                  False otherwise.

        Raises:
            aiohttp.ClientError: If the API request fails.
        """
        self._ensure_authenticated()

        query = """
        mutation ($id: Int) {
            DeleteMediaListEntry(id: $id) {
                deleted
            }
        }
        """

        if self.dry_run:
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping anime entry "
                f"deletion $${{anilist_id: {media_id}}}$$"
            )
            return False

        variables = MediaList(
            id=entry_id, media_id=media_id, user_id=self.user.id
        ).model_dump_json(exclude_none=True)

        response = await self._make_request(query, variables)
        delete_response = response["data"]["DeleteMediaListEntry"]

        with contextlib.suppress(KeyError):
            del self.offline_anilist_entries[media_id]

        return delete_response["deleted"]

    async def search_anime(
        self,
        search_str: str,
        is_movie: bool,
        episodes: int | None = None,
        limit: int = 10,
    ) -> AsyncIterator[Media]:
        """Search for anime on AniList with filtering capabilities.

        Performs a search query and filters results based on media format and episode
        count. Uses local caching through _search_anime() to optimize repeated searches.

        Args:
            search_str (str): Title or keywords to search for.
            is_movie (bool): If True, searches only for movies and specials. If False,
                searches for TV series, OVAs, and ONAs.
            episodes (int | None): Filter results to match this episode count. If None,
                returns all results.
            limit (int): Maximum number of results to return.

        Yields:
            Media: Filtered matching anime entries, sorted by relevance.

        Raises:
            aiohttp.ClientError: If the API request fails.
        """
        log.debug(
            f"{self.__class__.__name__}: Searching for {
                'movie' if is_movie else 'show'
            } "
            f"with title $$'{search_str}'$$ that is releasing and has {
                episodes or 'unknown'
            } episodes"
        )

        res = await self._search_anime(search_str, is_movie, limit)
        for m in res:
            if (
                m.status == MediaStatus.RELEASING
                or m.episodes == episodes
                or not episodes
            ):
                yield m

    @alru_cache(maxsize=None, ttl=604800)
    async def _search_anime(
        self,
        search_str: str,
        is_movie: bool,
        limit: int = 10,
    ) -> list[Media]:
        """Cached helper function for anime searches.

        Makes the actual GraphQL query to search for anime and caches results
        to reduce API calls for repeated searches.

        Args:
            search_str (str): Title or keywords to search for.
            is_movie (bool): If True, limits to movies and specials. If False, limits
                to TV series, OVAs, and ONAs.
            limit (int): Maximum number of results to return. Defaults to 10.

        Returns:
            list[Media]: List of matching anime entries, unfiltered.

        Raises:
            aiohttp.ClientError: If the API request fails.
        """
        query = f"""
            query ($search: String, $formats: [MediaFormat], $limit: Int) {{
                Page(perPage: $limit) {{
                    media(search: $search, type: ANIME, format_in: $formats) {{
                        {Media.model_dump_graphql()}
                    }}
                }}
            }}
        """

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

        response = await self._make_request(query, variables)
        return [Media(**m) for m in response["data"]["Page"]["media"]]

    async def get_anime(
        self,
        anilist_id: int,
    ) -> Media:
        """Retrieves detailed information about a specific anime.

        Attempts to fetch anime data from local cache first, falling back to
        an API request if not found in cache.

        Args:
            anilist_id (int): The AniList ID of the anime to retrieve.

        Returns:
            Media: Detailed information about the requested anime.

        Raises:
            aiohttp.ClientError: If the API request fails.
        """
        if anilist_id in self.offline_anilist_entries:
            log.debug(
                f"{self.__class__.__name__}: Pulling AniList data from local cache "
                f"$${{anilist_id: {anilist_id}}}$$"
            )
            return self.offline_anilist_entries[anilist_id]

        query = f"""
        query ($id: Int) {{
            Media(id: $id, type: ANIME) {{
                {Media.model_dump_graphql()}
            }}
        }}
        """

        log.debug(
            f"{self.__class__.__name__}: Pulling AniList data from API "
            f"$${{anilist_id: {anilist_id}}}$$"
        )

        response = await self._make_request(query, {"id": anilist_id})
        result = Media(**response["data"]["Media"])

        self.offline_anilist_entries[anilist_id] = result

        return result

    async def batch_get_anime(self, anilist_ids: list[int]) -> list[Media]:
        """Retrieves detailed information about a list of anime.

        Attempts to fetch anime data from local cache first, falling back to
        batch API requests for entries not found in cache. Processes requests
        in batches of 10 to avoid overwhelming the API.

        Args:
            anilist_ids (list[int]): The AniList IDs of the anime to retrieve.

        Returns:
            list[Media]: Detailed information about the requested anime.

        Raises:
            aiohttp.ClientError: If the API request fails.
        """
        BATCH_SIZE = 50

        if not anilist_ids:
            return []

        result: list[Media] = []
        missing_ids = []

        cached_ids = [id for id in anilist_ids if id in self.offline_anilist_entries]
        if cached_ids:
            log.debug(
                f"{self.__class__.__name__}: Pulling AniList data from local cache in "
                f"batched mode $${{anilist_ids: {cached_ids}}}$$"
            )
            result.extend(self.offline_anilist_entries[id] for id in cached_ids)

        missing_ids = [
            id for id in anilist_ids if id not in self.offline_anilist_entries
        ]
        if not missing_ids:
            return result

        for i in range(0, len(missing_ids), BATCH_SIZE):
            batch_ids = missing_ids[i : i + BATCH_SIZE]
            log.debug(
                f"{self.__class__.__name__}: Pulling AniList data from API in batched "
                f"mode $${{anilist_ids: {batch_ids}}}$$"
            )

            query = f"""
            query BatchGetAnime($ids: [Int]) {{
            Page(perPage: {len(batch_ids)}) {{
                media(id_in: $ids, type: ANIME) {{
                    {Media.model_dump_graphql()}
                }}
            }}
            }}
            """

            variables = {"ids": batch_ids}
            response = await self._make_request(query, variables)

            media_list = response.get("data", {}).get("Page", {}).get("media", []) or []
            media_by_id = {m["id"]: Media(**m) for m in media_list}

            for anilist_id in batch_ids:
                media = media_by_id.get(anilist_id)
                if not media:
                    continue
                self.offline_anilist_entries[anilist_id] = media
                result.append(media)

        return result

    async def backup_anilist(self) -> None:
        """Creates a JSON backup of the user's AniList data.

        Fetches all anime entries from the user's lists and saves them to a JSON file.
        Implements a rotating backup system that maintains backups for
        BACKUP_RETENTION_DAYS.

        The backup includes:
            - User information
            - All non-custom anime lists
            - Detailed information about each anime entry

        Raises:
            aiohttp.ClientError: If the API request fails.
            OSError: If unable to create backup directory or write backup file.
        """
        self._ensure_authenticated()
        if self.backup_dir is None:
            raise aiohttp.ClientError(
                f"{self.__class__.__name__}: backup_dir must be set for backups"
            )

        query = f"""
        query MediaListCollection($userId: Int, $type: MediaType, $chunk: Int) {{
            MediaListCollection(userId: $userId, type: $type, chunk: $chunk) {{
                {MediaListCollectionWithMedia.model_dump_graphql()}
            }}
        }}
        """

        data = MediaListCollectionWithMedia(user=self.user, has_next_chunk=True)
        variables: dict[str, Any] = {
            "userId": self.user.id,
            "type": "ANIME",
            "chunk": 0,
        }

        while data.has_next_chunk:
            response = await self._make_request(query, variables)
            collection_data = response["data"]["MediaListCollection"]

            new_data = MediaListCollectionWithMedia(**collection_data)

            data.has_next_chunk = new_data.has_next_chunk
            variables["chunk"] += 1

            for li in new_data.lists:
                if li.is_custom_list:
                    continue
                data.lists.append(li)
                for entry in li.entries:
                    self.offline_anilist_entries[entry.media_id] = (
                        self._media_list_entry_to_media(entry)
                    )

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_filename = f"plexanibridge-{self.profile_name}.{timestamp}.json"
        backup_file = self.backup_dir / backup_filename

        if not backup_file.parent.exists():
            backup_file.parent.mkdir(parents=True)

        # To compress the backup file, remove the unecessary media field from each entry
        sanitized_lists: list[MediaListGroup] = []
        for li in data.lists:
            sanitized_entries: list[MediaList] = []
            for entry in li.entries:
                sanitized_entry = MediaList(
                    **{
                        field: getattr(entry, field)
                        for field in MediaList.model_fields
                        if hasattr(entry, field)
                    }
                )
                sanitized_entries.append(sanitized_entry)

            sanitized_lists.append(
                MediaListGroup(
                    entries=sanitized_entries,
                    name=li.name,
                    is_custom_list=li.is_custom_list,
                    is_split_completed_list=li.is_split_completed_list,
                    status=li.status,
                )
            )

        data_without_media = MediaListCollection(
            user=data.user,
            lists=sanitized_lists,
            has_next_chunk=data.has_next_chunk,
        )

        backup_file.write_text(data_without_media.model_dump_json())
        log.info(
            f"{self.__class__.__name__}: Exported AniList data to $$'{backup_file}'$$"
        )

        cutoff_date = datetime.now() - timedelta(days=self.BACKUP_RETENTION_DAYS)

        retention_pattern = f"plexanibridge-{self.profile_name}.*.json"
        for file in self.backup_dir.glob(retention_pattern):
            file_mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if file_mtime < cutoff_date:
                file.unlink()
                log.debug(f"{self.__class__.__name__}: Deleted old backup '{file}'")

    def _media_list_entry_to_media(self, media_list_entry: MediaListWithMedia) -> Media:
        """Converts a MediaListWithMedia object to a Media object.

        Creates a new Media object that combines the user's list entry data
        with the anime's metadata.

        Args:
            media_list_entry (MediaListWithMedia): Combined object containing both list
                entry and media information.

        Returns:
            Media: New Media object containing all relevant fields from both the list
                entry and media information.

        Note:
            This is an internal helper method used primarily by backup_anilist().
        """
        return Media(
            media_list_entry=MediaList(
                **{
                    field: getattr(media_list_entry, field)
                    for field in MediaList.model_fields
                    if hasattr(media_list_entry, field)
                }
            ),
            **{
                field: getattr(media_list_entry.media, field)
                for field in Media.model_fields
                if hasattr(media_list_entry.media, field)
            },
        )

    @anilist_limiter()
    async def _make_request(
        self, query: str, variables: dict | str | None = None, retry_count: int = 0
    ) -> dict:
        """Makes a rate-limited request to the AniList GraphQL API.

        Handles rate limiting, authentication, and automatic retries for
        rate limit exceeded responses.

        Args:
            query (str): GraphQL query string
            variables (dict | str): Variables for the GraphQL query
            retry_count (int): Number of retries attempted (used for temporary errors)

        Returns:
            dict: JSON response from the API

        Raises:
            aiohttp.ClientError: If the request fails for any reason other than rate
                limiting

        Note:
            - Implements rate limiting of 30 requests per minute
            - Automatically retries after waiting if rate limit is exceeded
            - Includes Authorization header using the stored token
        """
        if retry_count >= 3:
            raise aiohttp.ClientError("Failed to make request after 3 tries")

        if variables is None:
            variables = {}

        session = await self._get_session()

        try:
            async with session.post(
                self.API_URL,
                json={"query": query, "variables": variables},
            ) as response:
                if response.status == 429:  # Handle rate limit retries
                    retry_after = int(response.headers.get("Retry-After", 60))
                    log.warning(
                        f"{self.__class__.__name__}: Rate limit exceeded, waiting "
                        f"{retry_after} seconds"
                    )
                    await asyncio.sleep(retry_after + 1)
                    return await self._make_request(
                        query=query, variables=variables, retry_count=retry_count + 1
                    )
                elif response.status == 502:  # Bad Gateway
                    log.warning(
                        f"{self.__class__.__name__}: Received 502 Bad Gateway, retrying"
                    )
                    await asyncio.sleep(1)
                    return await self._make_request(
                        query=query, variables=variables, retry_count=retry_count + 1
                    )

                try:
                    response.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    log.error(
                        f"{self.__class__.__name__}: Failed to make request to AniList "
                        f"API"
                    )
                    response_text = await response.text()
                    log.error(f"\t\t{response_text}")
                    raise e

                return await response.json()

        except (TimeoutError, aiohttp.ClientError):
            log.error(
                f"{self.__class__.__name__}: Connection error while making request to "
                f"AniList API"
            )
            await asyncio.sleep(1)
            return await self._make_request(
                query=query, variables=variables, retry_count=retry_count + 1
            )
