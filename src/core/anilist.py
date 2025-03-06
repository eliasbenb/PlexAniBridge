from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent
from time import sleep

import requests
from cachetools.func import ttl_cache

from src import log
from src.models.anilist import (
    Media,
    MediaFormat,
    MediaList,
    MediaListCollectionWithMedia,
    MediaListWithMedia,
    MediaStatus,
    User,
)
from src.utils.rate_limiter import RateLimiter


class AniListClient:
    """Client for interacting with the AniList GraphQL API

    This client provides methods to interact with the AniList GraphQL API, including searching for anime,
    updating user lists, and managing anime entries. It implements rate limiting and local caching
    to optimize API usage.

    Attributes:
        API_URL (str): The AniList GraphQL API endpoint
        BACKUP_RETENTION_DAYS (int): Number of days to retain backup files
        anilist_token (str): Authentication token for AniList API
        backup_dir (Path): Directory where backup files are stored
        dry_run (bool): If True, skips making actual API modifications
        rate_limiter (RateLimiter): Handles API request rate limiting
        user (User): Authenticated user's information
        offline_anilist_entries (dict[int, Media]): Cache of anime entries
    """

    API_URL = "https://graphql.anilist.co"
    BACKUP_RETENTION_DAYS = 7

    def __init__(self, anilist_token: str, backup_dir: Path, dry_run: bool) -> None:
        """Initialize the AniList client.

        Args:
            anilist_token (str): Authentication token for AniList API
            backup_dir (Path): Directory path where backup files will be stored
            dry_run (bool): If True, simulates API calls without making actual changes
        """
        self.anilist_token = anilist_token
        self.backup_dir = backup_dir
        self.dry_run = dry_run

        self.rate_limiter = RateLimiter(self.__class__.__name__, requests_per_minute=90)
        self.user = self.get_user()
        self.user_tz = self.get_user_tz()

        self.offline_anilist_entries: dict[int, Media] = {}
        self.backup_anilist()

    def reinit(self) -> None:
        """Reinitializes the AniList client after token refresh.

        Reinitializes the client with a new authentication token and user information.
        Clears the local cache and backups to prevent conflicts with outdated data.
        """
        self.user = self.get_user()
        self.user_tz = self.get_user_tz()

        self.offline_anilist_entries.clear()
        self.backup_anilist()

    def get_user(self) -> User:
        """Retrieves the authenticated user's information from AniList.

        Makes a GraphQL query to fetch detailed user information including ID, name,
        and other profile data for the authenticated user.

        Returns:
            User: Object containing the authenticated user's information

        Raises:
            requests.HTTPError: If the API request fails
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

    def get_user_tz(self) -> timezone:
        """Returns the authenticated user's timezone.

        Returns:
            timezone: The timezone of the authenticated user
        """
        try:
            hours, minutes = map(int, self.user.options.timezone.split(":"))
            return timezone(timedelta(hours=hours, minutes=minutes))
        except (AttributeError, ValueError):
            return timezone.utc

    def update_anime_entry(self, media_list_entry: MediaList) -> None:
        """Updates an anime entry on the authenticated user's list.

        Sends a mutation to modify an existing anime entry in the user's list with new
        values for status, score, progress, etc.

        Args:
            media_list_entry (MediaList): Updated AniList entry to save

        Raises:
            requests.HTTPError: If the API request fails
        """
        query = dedent(f"""
        mutation ($mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int, $repeat: Int, $notes: String, $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput) {{
            SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score, progress: $progress, repeat: $repeat, notes: $notes, startedAt: $startedAt, completedAt: $completedAt) {{
{MediaListWithMedia.model_dump_graphql(indent_level=3)}
            }}
        }}
        """).strip()

        if self.dry_run:  # Skip the request, only log the variables
            log.info(
                f"{self.__class__.__name__}: Dry run enabled, skipping anime entry update $${{anilist_id: {media_list_entry.media_id}}}$$"
            )
            return None

        variables = media_list_entry.model_dump_json(exclude_none=True)

        response = self._make_request(query, variables)["data"]["SaveMediaListEntry"]

        self.offline_anilist_entries[media_list_entry.media_id] = (
            self._media_list_entry_to_media(MediaListWithMedia(**response))
        )

    def delete_anime_entry(self, entry_id: int, media_id: int) -> bool:
        """Deletes an anime entry from the authenticated user's list.

        Sends a mutation to remove a specific anime entry from the user's list.

        Args:
            entry_id (int): The AniList ID of the list entry to delete
            media_id (int): The AniList ID of the anime being deleted

        Returns:
            bool: True if the entry was successfully deleted and not in dry run mode, False otherwise

        Raises:
            requests.HTTPError: If the API request fails
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

        try:
            del self.offline_anilist_entries[media_id]
        except KeyError:
            pass

        return response["deleted"]

    @ttl_cache(maxsize=None, ttl=86400)
    def search_anime(
        self,
        search_str: str,
        is_movie: bool,
        episodes: int | None = None,
        limit: int = 10,
    ) -> list[Media]:
        """Searches for anime on AniList with filtering capabilities.

        Performs a search query and filters results based on media format and episode count.
        Uses local caching through _search_anime() to optimize repeated searches.

        Args:
            search_str (str): Title or keywords to search for
            is_movie (bool): If True, searches only for movies and specials. If False, searches for TV series, OVAs, and ONAs
            episodes (int | None): Filter results to match this episode count. If None, returns all results
            limit (int): Maximum number of results to return. Defaults to 10

        Returns:
            list[Media]: Filtered list of matching anime entries, sorted by relevance

        Raises:
            requests.HTTPError: If the API request fails
        """
        log.debug(
            f"{self.__class__.__name__}: Searching for {'movie' if is_movie else 'show'} "
            f"with title $$'{search_str}'$$ that is releasing and has {episodes or 'unknown'} episodes"
        )

        res = self._search_anime(search_str, is_movie, limit)
        return [
            m
            for m in res
            if m.status == MediaStatus.RELEASING
            or m.episodes == episodes
            or not episodes
        ]

    @ttl_cache(maxsize=None, ttl=604800)
    def _search_anime(
        self,
        search_str: str,
        is_movie: bool,
        limit: int = 10,
    ) -> list[Media]:
        """Cached helper function for anime searches.

        Makes the actual GraphQL query to search for anime and caches results
        to reduce API calls for repeated searches.

        Args:
            search_str (str): Title or keywords to search for
            is_movie (bool): If True, limits to movies and specials. If False, limits to TV series, OVAs, and ONAs
            limit (int): Maximum number of results to return. Defaults to 10

        Returns:
            list[Media]: List of matching anime entries, unfiltered

        Raises:
            requests.HTTPError: If the API request fails

        Note:
            This method is cached using functools.cache to optimize repeated searches
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
        anilist_id: int,
    ) -> Media:
        """Retrieves detailed information about a specific anime.

        Attempts to fetch anime data from local cache first, falling back to
        an API request if not found in cache.

        Args:
            anilist_id (int): The AniList ID of the anime to retrieve

        Returns:
            Media: Detailed information about the requested anime

        Raises:
            requests.HTTPError: If the API request fails

        Note:
            Results are cached in self.offline_anilist_entries for future use
        """
        if anilist_id in self.offline_anilist_entries:
            log.debug(
                f"{self.__class__.__name__}: Pulling AniList data from local cache $${{anilist_id: {anilist_id}}}$$"
            )
            return self.offline_anilist_entries[anilist_id]

        query = dedent(f"""
        query ($id: Int) {{
            Media(id: $id, type: ANIME) {{
{Media.model_dump_graphql(indent_level=3)}
            }}
        }}
        """).strip()

        log.debug(
            f"{self.__class__.__name__}: Pulling AniList data from API $${{anilist_id: {anilist_id}}}$$"
        )

        response = self._make_request(query, {"id": anilist_id})
        result = Media(**response["data"]["Media"])

        self.offline_anilist_entries[anilist_id] = result

        return result

    def backup_anilist(self) -> None:
        """Creates a JSON backup of the user's AniList data.

        Fetches all anime entries from the user's lists and saves them to a JSON file.
        Implements a rotating backup system that maintains backups for BACKUP_RETENTION_DAYS.

        The backup includes:
            - User information
            - All non-custom anime lists
            - Detailed information about each anime entry

        Raises:
            requests.HTTPError: If the API request fails
            OSError: If unable to create backup directory or write backup file

        Note:
            - Backup files are named: plexanibridge-{username}.{number}.json
            - Old backups exceeding BACKUP_RETENTION_DAYS are automatically deleted
            - Skips custom lists to focus on standard watching status lists
        """
        query = dedent(f"""
        query MediaListCollection($userId: Int, $type: MediaType, $chunk: Int) {{
            MediaListCollection(userId: $userId, type: $type, chunk: $chunk) {{
{MediaListCollectionWithMedia.model_dump_graphql(indent_level=3)}
            }}
        }}
        """).strip()

        data = MediaListCollectionWithMedia(user=self.user, has_next_chunk=True)
        variables = {"userId": self.user.id, "type": "ANIME", "chunk": 0}

        while data.has_next_chunk:
            response = self._make_request(query, variables)["data"][
                "MediaListCollection"
            ]

            new_data = MediaListCollectionWithMedia(**response)

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

    def _media_list_entry_to_media(self, media_list_entry: MediaListWithMedia) -> Media:
        """Converts a MediaListWithMedia object to a Media object.

        Creates a new Media object that combines the user's list entry data
        with the anime's metadata.

        Args:
            media_list_entry (MediaListWithMedia): Combined object containing both list entry and media information

        Returns:
            Media: New Media object containing all relevant fields from both the list entry and media information

        Note:
            This is an internal helper method used primarily by backup_anilist()
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

    def _make_request(self, query: str, variables: dict | str | None = None) -> dict:
        """Makes a rate-limited request to the AniList GraphQL API.

        Handles rate limiting, authentication, and automatic retries for
        rate limit exceeded responses.

        Args:
            query (str): GraphQL query string
            variables (dict | str | None): Variables for the GraphQL query

        Returns:
            dict: JSON response from the API

        Raises:
            requests.HTTPError: If the request fails for any reason other than rate limiting

        Note:
            - Implements rate limiting of 90 requests per minute
            - Automatically retries after waiting if rate limit is exceeded
            - Includes Authorization header using the stored token
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
                f"{self.__class__.__name__}: Failed to make request to AniList API: ",
                exc_info=True,
            )
            log.error(f"\t\t{response.text}")
            raise e

        return response.json()
