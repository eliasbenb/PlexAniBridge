from datetime import datetime, timedelta
from math import isnan
from typing import TypeAlias
from urllib.parse import urlparse
from xml.etree import ElementTree

import plexapi.utils
import requests
from cachetools.func import lru_cache
from plexapi.library import MovieSection, ShowSection
from plexapi.myplex import MyPlexUser
from plexapi.server import PlexServer
from plexapi.video import (
    Episode,
    EpisodeHistory,
    Movie,
    MovieHistory,
    Season,
    Show,
)
from tzlocal import get_localzone

from src import log
from src.settings import PlexMetadataSource
from src.utils.requests import SelectiveVerifySession

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
        self._init_online_client()
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
        parsed_url = urlparse(self.plex_url)
        session = None
        if parsed_url.scheme == "https":
            session = SelectiveVerifySession(whitelist=[parsed_url.hostname])

        self.admin_client = PlexServer(self.plex_url, self.plex_token, session)

    def _init_online_client(self) -> None:
        """Initializes the Plex client for the online metadata source.

        Handles authentication and client setup for the online metadata source.
        """
        if self.plex_metadata_source == PlexMetadataSource.ONLINE:
            self.online_client = PlexMetadataServer(self.plex_url, self.plex_token)
        else:
            self.online_client = None

    def _init_user_client(self) -> PlexServer:
        """Initializes the Plex client for the specified user account.

        Handles authentication and client setup for different user types:
        - Admin users (identified by username, email, or title)
        - Regular Plex users (identified by username or email)
        - Home users (identified by title when username is not present)

        Returns:
            PlexServer: Initialized Plex client for the user account
        """
        admin_account = self.admin_client.myPlexAccount()
        self.is_admin_user = self.plex_user.lower() in (
            (admin_account.username or "").lower(),
            (admin_account.email or "").lower(),
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

            try:
                self.user_client = self.admin_client.switchUser(self.plex_user)
                self.user_account_id = self._match_plex_user(
                    self.plex_user, admin_account.users()
                ).id
            except Exception as e:
                raise ValueError(
                    f"{self.__class__.__name__}: Failed to switch to user $$'{self.plex_user}'$$"
                ) from e

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

    def _match_plex_user(self, plex_user: str, users: list[MyPlexUser]) -> MyPlexUser:
        """Matches the specified Plex user to a MyPlexUser object.

        Args:
            plex_user (str): Username, email, or title of the Plex user to match
            users (list[MyPlexUser]): List of Plex users to search

        Returns:
            MyPlexUser: MyPlexUser object for the specified user
        """
        plex_user_lower = plex_user.lower()

        def is_home_user(u: MyPlexUser) -> bool:
            return u.title and not u.username and not u.email

        for u in users:
            if is_home_user(u):
                if plex_user_lower == (u.title or "").lower():
                    return u
            elif plex_user_lower in (
                (u.username or "").lower(),
                (u.email or "").lower(),
            ):
                return u

        raise ValueError(
            f"{self.__class__.__name__}: User $$'{self.plex_user}'$$ not found "
            f"in Plex users list"
        )

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
        if self.plex_sections:
            return [
                sections[title] for title in self.plex_sections if title in sections
            ]
        return list(sections.values())

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
                min_last_modified = min_last_modified - timedelta(seconds=30)

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
                        {"viewCount>>": 0},
                        {
                            "lastRatedAt>>=": datetime(
                                1970, 1, 1, tzinfo=get_localzone()
                            )
                        },
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

    @lru_cache(maxsize=32)
    def get_continue_watching_hub(
        self, section: MovieSection | ShowSection
    ) -> list[Movie | Episode]:
        """Retrieves all items in the Continue Watching hub.

        Args:
            section (MovieSection | ShowSection): The library section to query

        Returns:
            list[Movie | Episode]
        """
        return section.continueWatching()

    def get_continue_watching(self, item: Movie | Show) -> Movie | Episode:
        """Retrieves all items in the Continue Watching hub.

        Args:
            item (Movie | Show): The media to get any continue watching items for

        Returns:
            Movie | Episode | None: The continue watching item if found, None otherwise
        """
        if self.is_online_user:
            return None

        if item.type == "movie":
            return next(
                (
                    e
                    for e in self.get_continue_watching_hub(item.section())
                    if item.ratingKey == e.ratingKey
                ),
                None,
            )
        elif item.type == "show":
            return next(
                (
                    e
                    for e in self.get_continue_watching_hub(item.section())
                    if item.ratingKey == e.grandparentRatingKey
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
            args = {
                "metadataItemID": item.ratingKey,
                "accountID": self.user_account_id,
                "sort": "viewedAt:asc",
            }
            return self.admin_client.fetchItems(
                f"/status/sessions/history/all{plexapi.utils.joinArgs(args)}"
            )

        try:
            data = self.community_client.get_watch_activity(
                self._guid_to_key(item.guid)
            )
            history: list[EpisodeHistory] = []
            for entry in data:
                metadata = entry["metadataItem"]
                user = entry["userV2"]

                attrib = {
                    "accountID": str(user["id"]),
                    "deviceID": "",
                    "historyKey": f"/status/sessions/history/{entry['id']}",
                    "ratingKey": metadata["id"],
                    "guid": metadata["id"],
                    "title": metadata["title"],
                }

                if metadata["type"] == "EPISODE":
                    attrib["parentGuid"] = metadata["parent"]["id"]
                    attrib["grandparentGuid"] = metadata["grandparent"]["id"]
                    attrib["index"] = metadata["index"]
                    attrib["parentIndex"] = metadata["parent"]["index"]
                    attrib["parentTitle"] = metadata["parent"]["title"]
                    attrib["grandparentTitle"] = metadata["grandparent"]["title"]

                    history_data = ElementTree.Element("History", attrib=attrib)
                    h = EpisodeHistory(
                        server=self.online_client._server, data=history_data
                    )
                    h.parentRatingKey = metadata["parent"]["id"]
                    h.grandparentRatingKey = metadata["grandparent"]["id"]
                elif metadata["type"] == "MOVIE":
                    history_data = ElementTree.Element("History", attrib=attrib)
                    h = MovieHistory(
                        server=self.online_client._server, data=history_data
                    )

                h.ratingKey = metadata["id"]
                h.viewedAt = (
                    datetime.fromisoformat(entry["date"])
                    .astimezone(get_localzone())
                    .replace(tzinfo=None)
                )
                history.append(h)

            return sorted(history, key=lambda x: x.viewedAt)
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
        return []

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
