from datetime import datetime, timedelta, timezone
from math import isnan
from typing import TypeAlias
from xml.etree import ElementTree

import requests
from cachetools.func import lru_cache
from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.video import (
    Episode,
    EpisodeHistory,
    Movie,
    MovieHistory,
    PlexHistory,
    Season,
    Show,
)
from tzlocal import get_localzone

from src import log
from src.settings import PlexMetadataSource

from .plexapi.community import PlexCommunityClient
from .plexapi.metadata import PlexMetadataServer

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
        self._init_community_client()

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
        self.admin_client = PlexServer(self.plex_url, self.plex_token)
        self.online_client = (
            PlexMetadataServer(self.plex_url, self.plex_token)
            if self.plex_metadata_source == PlexMetadataSource.ONLINE
            else None
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
        self.is_online_user = (
            self.plex_metadata_source == PlexMetadataSource.ONLINE
            and self.is_admin_user
        )

        if self.is_online_user:
            self.user_client = self.online_client
            self.user_account_id = 1
        elif self.is_admin_user:
            self.user_client = self.admin_client
            self.user_account_id = 1
        else:
            if self.plex_metadata_source == PlexMetadataSource.ONLINE:
                log.warning(
                    f"{self.__class__.__name__}: PLEX_METADATA_SOURCE=online was configured "
                    f"but the user $$'{self.plex_user}'$$ is not an admin user. Online data "
                    "will not be available for this user."
                )

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

    def _init_community_client(self) -> None:
        """Initializes the Plex Community API client.

        Handles authentication and client setup for the Plex Community API.
        """
        self.community_client = PlexCommunityClient(self.plex_token)

    def _get_on_deck_window(self) -> timedelta:
        """Gets the configured cutoff time for Continue Watching items on Plex.

        This setting is server-wide and can only be configured by the admin of the server.

        Returns:
            timedelta: Time delta for the cutoff duration
        """
        return timedelta(weeks=self.admin_client.settings.get("onDeckWindow").value)

    def _guid_to_key(self, guid: str) -> int:
        """Converts a Plex GUID to a Plex rating key.

        Args:
            guid (str): Plex GUID to convert

        Returns:
            int: Plex rating key
        """
        return guid.rsplit("/", 1)[-1]

    def get_sections(self) -> list[Section]:
        """Retrieves configured Plex library sections.

        Returns only the sections that are specified in self.plex_sections,
        filtered from all available library sections.

        Returns:
            list[MovieSection] | list[ShowSection]: List of configured library sections.
                Returns empty list if no sections match the configuration.
        """
        log.debug(f"{self.__class__.__name__}: Getting all sections")

        sections = {
            section.title: section for section in self.user_client.library.sections()
        }
        return [sections[title] for title in self.plex_sections if title in sections]

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
            list[Media]: List of media items matching the criteria
        """
        filters = {"and": []}

        if min_last_modified:
            if self.is_online_user:
                min_last_modified = min_last_modified + timedelta(seconds=90)

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
        if not item.guid:
            return None

        try:
            log.debug(
                f"{self.__class__.__name__}: Getting reviews for {item.type} "
                f"$$'{item.title}'$$ $${{ plex_id: {item.guid}}}$$"
            )
            return self.community_client.get_reviews(self._guid_to_key(item.guid))
        except requests.HTTPError:
            log.error(
                f"Failed to get review for {item.type} $$'{item.title}'$$ "
                f"$${{key: {item.ratingKey}, plex_id: {item.guid}}}$$",
                exc_info=True,
            )
            return None
        except Exception:
            log.error(
                f"Failed to parse review for {item.type} $$'{item.title}'$$ "
                f"$${{key: {item.ratingKey}, plex_id: {item.guid}}}$$",
                exc_info=True,
            )
            return None

    @lru_cache(maxsize=1)
    def _continue_watching_hub(self) -> list[Movie | Episode]:
        """Retrieves all items in the Continue Watching hub.

        Returns:
            list[Movie | Episode]
        """
        return self.user_client.fetchItems("/hubs/continueWatching/items")

    def get_continue_watching(self, item: Movie | Show) -> Movie | Episode:
        """Retrieves all items in the Continue Watching hub.

        Args:
            item (Movie | Show): The media to get any continue watching items for

        Returns:
            Movie | Episode | None: The continue watching item if found, None otherwise
        """
        rating_key = item.ratingKey
        if self.is_online_user:
            rating_key = getattr(item, "_ratingKey", None)
        if not rating_key:
            return []

        return next(
            (
                e
                for e in self._continue_watching_hub()
                if rating_key == e.ratingKey
                or rating_key == getattr(e, "grandParentRatingKey", None)
            ),
            None,
        )

    @lru_cache(maxsize=32)
    def get_history(
        self,
        item: Media,
    ) -> list[History]:
        """Retrieves watch history for a media item.

        Args:
            item (Media): Media item(s) to get history for

        Returns:
            list[History]: Watch history entries for the item

        Note:
            Results are cached using functools.cache decorator
        """
        if not self.is_online_user:
            return item.history()

        try:
            data = self.community_client.get_watch_activity(
                self._guid_to_key(item.guid)
            )
            history = []
            for entry in data:
                metadata = entry["metadataItem"]
                user = entry["userV2"]

                history_data = ElementTree.Element(
                    "History",
                    attrib={
                        "accountID": str(user["id"]),
                        "deviceID": "",
                        "historyKey": f"/status/sessions/history/{entry['id']}",
                        "viewedAt": entry["date"],
                        "grandparentTitle": item.grandparentTitle
                        if hasattr(item, "grandparentTitle")
                        else "",
                        "index": item.index if hasattr(item, "index") else "",
                        "parentIndex": item.parentIndex
                        if hasattr(item, "parentIndex")
                        else "",
                    },
                )
                history_kwargs = {
                    "server": self.online_client._server,
                    "data": history_data,
                }

                history.append(
                    EpisodeHistory(**history_kwargs)
                    if metadata["type"] == "EPISODE"
                    else MovieHistory(**history_kwargs)
                    if metadata["type"] == "MOVIE"
                    else PlexHistory(**history_kwargs)
                )
            return history
        except requests.HTTPError:
            log.error(
                f"Failed to get watch hsitory for {item.type} $$'{item.title}'$$ "
                f"$${{key: {item.ratingKey}, plex_id: {item.guid}}}$$",
                exc_info=True,
            )
        except Exception:
            log.error(
                f"Failed to parse watch hsitory for {item.type} $$'{item.title}'$$ "
                f"$${{key: {item.ratingKey}, plex_id: {item.guid}}}$$",
                exc_info=True,
            )
        finally:
            return []

    def get_first_history(self, item: Media) -> History | None:
        """Retrieves the oldest watch history entry for a media item.

        A convenience wrapper around get_history() that returns only the
        first (oldest) history entry.

        Args:
            item (Media): Media item to get history for

        Returns:
            History | None: Oldest history entry if found, None if no history exists
        """
        return min(self.get_history(item), key=lambda h: h.viewedAt, default=None)

    def get_last_history(self, item: Media) -> History | None:
        """Retrieves the most recent watch history entry for a media item.

        A convenience wrapper around get_history() that returns only the
        most recent history entry.

        Args:
            item (Media): Media item to get history for

        Returns:
            History | None: Most recent history entry if found, None if no history exists
        """
        return max(self.get_history(item), key=lambda h: h.viewedAt, default=None)

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

    def is_online_item(self, item: Media) -> bool:
        """Checks if a media item is from Plex's online API.

        Args:
            item (Media): Media item to check

        Returns:
            bool: True if item is from Plex's online servers, False otherwise
        """
        return isnan(item.librarySectionID)
