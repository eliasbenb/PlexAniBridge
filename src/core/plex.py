from datetime import datetime, timedelta, timezone
from textwrap import dedent
from typing import TypeAlias

import plexapi.utils
import requests
from cachetools.func import lru_cache
from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.video import Episode, EpisodeHistory, Movie, MovieHistory, Season, Show
from tzlocal import get_localzone

from src import log
from src.settings import PlexMetadataSource

from .plexapi.discover import DiscoverPlexServer

Media: TypeAlias = Movie | Show | Season | Episode
MediaHistory: TypeAlias = MovieHistory | EpisodeHistory
Section: TypeAlias = MovieSection | ShowSection
History: TypeAlias = MovieHistory | EpisodeHistory


class PlexClient:
    """Client for interacting with Plex Media Server and Plex API.

    This client provides methods to interact with both the Plex Media Server and Plex API,
    including accessing media sections, retrieving watch history, and managing user-specific
    features like watchlists and continue watching states.

    Attributes:
        plex_token (str): Authentication token for Plex
        plex_user (str): Username or email of the Plex user
        plex_url (str): Base URL of the Plex server
        plex_sections (list[str]): List of enabled Plex library section names
        admin_client (PlexServer): PlexServer instance with admin privileges
        user_client (PlexServer): PlexServer instance for the specified user
        is_admin_user (bool): Whether the specified user has admin privileges
        user_account_id (int): Unique identifier for the user account
    """

    def __init__(
        self,
        plex_token: str,
        plex_user: str,
        plex_url: str,
        plex_sections: list[str],
        plex_genres: list[str],
        plex_metadata_source: PlexMetadataSource,
    ) -> None:
        self.plex_token = plex_token
        self.plex_user = plex_user
        self.plex_url = plex_url
        self.plex_sections = plex_sections
        self.plex_genres = plex_genres
        self.plex_metadata_source = plex_metadata_source

        self._init_admin_client()
        self._init_user_client()

        self.on_deck_window = self._get_on_deck_window()

    def clear_cache(self) -> None:
        """Clears the cache for all decorated methods in the class."""
        for attr in dir(self):
            if callable(getattr(self, attr)) and hasattr(
                getattr(self, attr), "cache_clear"
            ):
                getattr(self, attr).cache_clear()

    def _init_admin_client(self) -> None:
        """Initializes the Plex client for the admin account.

        Handles authentication and client setup for the admin account.
        """
        self.admin_client = (
            PlexServer(self.plex_url, self.plex_token)
            if self.plex_metadata_source == PlexMetadataSource.LOCAL
            else DiscoverPlexServer(self.plex_url, self.plex_token)
        )

    def _init_user_client(self) -> PlexServer:
        """Initializes the Plex client for the specified user account.

        Handles authentication and client setup for different user types:
        - Admin users (identified by username, email, or title)
        - Regular Plex users (identified by username or email)
        - Home users (identified by title when username is not present)

        Returns:
            PlexServer: Initialized Plex client for the user account

        Note:
            Sets instance attributes is_admin_user and user_account_id
            Uses admin_client for admin users, creates new client for others
        """
        admin_account = self.admin_client.myPlexAccount()
        self.is_admin_user = self.plex_user in (
            admin_account.username,
            admin_account.email,
        ) or (admin_account.title == self.plex_user and not admin_account.username)

        if self.is_admin_user:
            self.user_client = self.admin_client
            self.user_account_id = 1
        else:
            self.user_client = self.admin_client.switchUser(self.plex_user)
            self.user_account_id = next(
                u.id
                for u in admin_account.users()
                if self.plex_user in (u.username, u.email)  # Regular user
                or (u.title == self.plex_user and not u.username)  # Home user
            )
        log.debug(
            f"{self.__class__.__name__}: Initialized Plex client for user "
            f"$$'{self.plex_user}'$$ $${{plex_account_id: {self.user_account_id}}}$$"
        )
        log.debug(
            f"{self.__class__.__name__}: User is an admin, using admin client"
            if self.is_admin_user
            else f"{self.__class__.__name__}: User is not an admin, using user client"
        )

    def _get_on_deck_window(self) -> timedelta:
        """Gets the configured cutoff time for Continue Watching items on Plex.

        This setting is server-wide and can only be configured by the admin of the server.

        Returns:
            timedelta: Time delta for the cutoff duration
        """
        return timedelta(weeks=self.admin_client.settings.get("onDeckWindow").value)

    def get_sections(self) -> list[Section]:
        """Retrieves configured Plex library sections.

        Returns only the sections that are specified in self.plex_sections,
        filtered from all available library sections.

        Returns:
            list[MovieSection] | list[ShowSection]: List of configured library sections.
                Returns empty list if no sections match the configuration.
        """
        log.debug(f"{self.__class__.__name__}: Getting all sections")

        return [
            section
            for section in self.user_client.library.sections()
            if section.title in self.plex_sections
        ]

    def get_section_items(
        self,
        section: Section,
        min_last_modified: datetime | None = None,
        require_watched: bool = False,
        **kwargs,
    ) -> list[Media]:
        """Retrieves items from a specified Plex library section with optional filtering.

        Args:
            section (Section): The library section to query
            min_last_modified (datetime | None): If provided, only returns items modified, viewed, or rated after this timestamp
            require_watched (bool): If True, only returns items that have been watched at least once. Defaults to False

        Returns:
            list[Movie] | list[Show]: List of media items matching the criteria
        """
        filters = {"and": []}

        if min_last_modified:
            log.debug(
                f"{self.__class__.__name__}: Filtering section $$'{section.title}'$$ by "
                f"items last updated, viewed, or rated after {min_last_modified.astimezone(get_localzone())}"
            )
            filters["and"].append(
                {
                    "or": [
                        {"addedAt>>=": min_last_modified},
                        {"updatedAt>>=": min_last_modified},
                        {"originallyAvailableAt>>=": min_last_modified},
                        {"lastViewedAt>>=": min_last_modified},
                        {"lastRatedAt>>=": min_last_modified},
                    ]
                }
            )

        if require_watched:
            log.debug(
                f"{self.__class__.__name__}: Filtering section $$'{section.title}'$$ by "
                f"items that have been watched"
            )
            filters["and"].append(
                {
                    "or": [
                        {"unwatched": False},
                        {"lastRatedAt>>=": datetime(1970, 1, 1, tzinfo=timezone.utc)},
                    ]
                }
            )

        if self.plex_genres:
            log.debug(
                f"{self.__class__.__name__}: Filtering section $$'{section.title}'$$ by "
                f"genres: {self.plex_genres}"
            )
            filters["and"].append({"genre": self.plex_genres})

        return section.search(filters=filters, **kwargs)

    @lru_cache(maxsize=32)
    def get_user_review(self, item: Media) -> str | None:
        """Retrieves user review for a media item from Plex community.

        Makes a GraphQL query to the Plex community API to fetch review content.
        Only works for admin users due to API limitations.

        Args:
            item (Media): Media item to get review for

        Returns:
            str | None: Review message if found, None if not found

        Raises:
            requests.HTTPError: If the API request fails
            KeyError: If the response format is unexpected
            ValueError: If the response cannot be parsed

        Note:
            Results are cached using functools.cache decorator
        """
        if not self.is_admin_user:
            return None

        query = dedent("""
        query GetReview($metadataID: ID!) {
            metadataReviewV2(metadata: {id: $metadataID}) {
                ... on ActivityReview {
                    message
                }
                ... on ActivityWatchReview {
                    message
                }
            }
        }
        """).strip()

        guid = item.guid.rsplit("/", 1)[-1]

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Plex-Token": self.plex_token,
        }

        log.debug(
            f"{self.__class__.__name__}: Getting reviews for {item.type} "
            f"$$'{item.title}'$$ $${{key: {item.ratingKey}, plex_id: {item.guid}}}$$"
        )

        try:
            response = requests.post(
                "https://community.plex.tv/api",
                headers=headers,
                json={
                    "query": query,
                    "variables": {
                        "metadataID": guid,
                    },
                    "operationName": "GetReview",
                },
            )
            response.raise_for_status()

            data = response.json()["data"]["metadataReviewV2"]
            if not data or "message" not in data:
                return None

            return data["message"]

        except requests.HTTPError:
            log.error(
                f"Failed to get review for {item.type} $$'{item.title}'$$ "
                f"$${{key: {item.ratingKey}, plex_id: {item.guid}}}$$: ",
                exc_info=True,
            )
            return None
        except (KeyError, ValueError):
            log.error(
                f"Failed to parse review for {item.type} $$'{item.title}'$$ "
                f"$${{key: {item.ratingKey}, plex_id: {item.guid}}}$$: ",
                exc_info=True,
            )
            return None

    @lru_cache(maxsize=32)
    def get_continue_watching(
        self, item: Media | None = None, **kwargs
    ) -> list[Movie | Episode]:
        """Retrieves all items in the Continue Watching hub.

        Args:
            item (Media | None): If provided, only returns items in Continue Watching for this media item

        Returns:
            list[Movie | Episode]
        """
        if item:
            key = {
                "movie": "ratingKey",
                "show": "grandparentRatingKey",
                "season": "parentRatingKey",
                "episode": "ratingKey",
            }.get(item.type, "ratingKey")
            kwargs.update({key: item.ratingKey})

        return self.user_client.fetchItems(
            "/hubs/continueWatching/items",
            **kwargs,
        )

    @lru_cache(maxsize=32)
    def get_history(
        self,
        item: Media,
        sort_asc: bool = True,
        **kwargs,
    ) -> list[History]:
        """Retrieves watch history for a media item.

        Args:
            item (Media): Media item(s) to get history for
            sort_asc (bool): Sort order for results
            **kwargs: Additional arguments to pass to fetchItems()

        Returns:
            list[History]: Watch history entries for the item

        Note:
            Results are cached using functools.cache decorator
        """
        if self.plex_metadata_source == PlexMetadataSource.DISCOVER:
            return []

        args = {
            "metadataItemID": item.ratingKey,
            "accountID": self.user_account_id,
            "sort": "viewedAt:asc" if sort_asc else "viewedAt:desc",
        }

        return self.admin_client.fetchItems(
            f"/status/sessions/history/all{plexapi.utils.joinArgs(args)}", **kwargs
        )

    def get_first_history(self, item: Media, **kwargs) -> History | None:
        """Retrieves the oldest watch history entry for a media item.

        A convenience wrapper around get_history() that returns only the
        first (oldest) history entry.

        Args:
            item (Media): Media item to get history for
            **kwargs: Additional arguments to pass to get_history()

        Returns:
            History | None: Oldest history entry if found, None if no history exists
        """
        return next(
            iter(self.get_history(item, maxresults=1, sort_asc=True, **kwargs)), None
        )

    def get_last_history(self, item: Media, **kwargs) -> History | None:
        """Retrieves the most recent watch history entry for a media item.

        A convenience wrapper around get_history() that returns only the
        most recent history entry.

        Args:
            item (Media): Media item to get history for
            **kwargs: Additional arguments to pass to get_history()

        Returns:
            History | None: Most recent history entry if found, None if no history exists
        """
        return next(
            iter(self.get_history(item, maxresults=1, sort_asc=False, **kwargs)), None
        )

    def is_on_watchlist(self, item: Movie | Show) -> bool:
        """Checks if a media item is on the user's watchlist.

        Args:
            item (Movie | Show): Media item to check

        Returns:
            bool: True if item is on watchlist, False otherwise
        """
        return bool(item.onWatchlist()) if self.is_admin_user else False

    def is_on_continue_watching(self, item: Media) -> bool:
        """Checks if a media item appears in the Continue Watching hub.

        Args:
            item (Movie | Show | Season): Media item to check
            **kwargs: Additional arguments to pass to get_continue_watching()

        Returns:
            bool: True if item appears in Continue Watching hub, False otherwise
        """
        return bool(self.get_continue_watching(item))

    def is_discover_item(self, item: Media) -> bool:
        """Checks if a media item is from the Discover server.

        Args:
            item (Movie | Show | Season | Episode): Media item to check

        Returns:
            bool: True if item is from Discover server, False otherwise
        """
        return isnan(item.librarySectionID)
