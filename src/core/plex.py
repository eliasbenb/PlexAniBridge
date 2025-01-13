from datetime import datetime, timedelta
from functools import cache
from textwrap import dedent

import plexapi.utils
import requests
from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.video import Episode, EpisodeHistory, Movie, MovieHistory, Season, Show

from src import log


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
    ) -> None:
        self.plex_token = plex_token
        self.plex_user = plex_user
        self.plex_url = plex_url
        self.plex_sections = plex_sections

        self.admin_client = PlexServer(plex_url, plex_token)
        self._init_user_client()
        self.on_deck_window = self._get_on_deck_window()

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

    def get_sections(self) -> list[MovieSection] | list[ShowSection]:
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
        section: MovieSection | ShowSection,
        min_last_modified: datetime | None = None,
        require_watched: bool = False,
    ) -> list[Movie] | list[Show]:
        """Retrieves items from a specified Plex library section with optional filtering.

        Args:
            section (MovieSection | ShowSection): The library section to query
            min_last_modified (datetime | None): If provided, only returns items modified, viewed, or rated after this timestamp
            require_watched (bool): If True, only returns items that have been watched at least once. Defaults to False

        Returns:
            list[Movie] | list[Show]: List of media items matching the criteria
        """
        filters = {"and": []}

        if min_last_modified:
            log.debug(
                f"{self.__class__.__name__}: Filtering section $$'{section.title}'$$ by "
                f"items last updated, viewed, or rated after {min_last_modified}"
            )
            filters["and"].append(
                {
                    "or": [
                        {"addedAt>>=": min_last_modified},
                        {"updatedAt>>=": min_last_modified},
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
            filters["and"].append({"unwatched": False})

        return section.search(filters=filters)

    @cache
    def get_user_review(self, item: Movie | Show | Season) -> str | None:
        """Retrieves user review for a media item from Plex community.

        Makes a GraphQL query to the Plex community API to fetch review content.
        Only works for admin users due to API limitations.

        Args:
            item (Movie | Show | Season): Media item to get review for

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

        if item.type not in ("movie", "show", "season"):
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

        guid = item.guid[13:] if item.type == "movie" else item.guid[12:]

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Plex-Token": self.plex_token,
        }

        log.debug(
            f"{self.__class__.__name__}: Getting reviews for {item.type} "
            f"$$'{item.title}'$$ $${{plex_id: {item.guid}}}$$"
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

        except requests.HTTPError as e:
            log.error(
                f"Failed to get review for {item.type} $$'{item.title}'$$ "
                f"{{plex_key: {item.ratingKey}}}",
                exc_info=e,
            )
            return None
        except (KeyError, ValueError) as e:
            log.error(
                f"Failed to parse review for {item.type} $$'{item.title}'$$ "
                f"{{plex_key: {item.ratingKey}}}",
                exc_info=e,
            )
            return None

    def get_episodes(self, season: Season, start: int, end: int) -> list[Episode]:
        """Retrieves episodes within a specified range for a season.

        Args:
            season (Season): The season to get episodes from
            start (int): Starting episode number (inclusive)
            end (int): Ending episode number (inclusive)

        Returns:
            list[Episode]: List of episodes with index between start and end

        Note:
            Episode numbers must match exactly - partial episodes or alternative numbering schemes are not supported
        """
        return [
            e
            for e in season.episodes(
                index__gte=start,
            )
            if e.index <= end
        ]

    def get_watched_episodes(
        self, season: Season, start: int, end: int
    ) -> list[Episode]:
        """Retrieves watched episodes within a specified range for a season.

        Similar to get_episodes() but only returns episodes that have been
        watched at least once (viewCount > 0).

        Args:
            season (Season): The season to get episodes from
            start (int): Starting episode number (inclusive)
            end (int): Ending episode number (inclusive)

        Returns:
            list[Episode]: List of watched episodes with index between start and end
        """
        return [
            e
            for e in season.episodes(
                index__gte=start,
                viewCount__gt=0,
            )
            if e.index <= end
        ]

    def get_continue_watching(
        self,
        item: Movie | Season,
        **kwargs,
    ) -> list[Movie] | list[Episode]:
        """Retrieves items from the 'Continue Watching' hub for a media item.

        Args:
            item (Movie | Season): Media item to check
            **kwargs: Additional arguments to pass to fetchItems()

        Returns:
            list[Movie] | list[Episode]: Media items in Continue Watching hub
        """
        if item.type == "movie":
            return self.user_client.fetchItems(
                "/hubs/continueWatching/items",
                ratingKey=item.ratingKey,
                **kwargs,
            )
        elif item.type == "season":
            return self.user_client.fetchItems(
                "/hubs/continueWatching/items",
                parentRatingKey=item.ratingKey,
                **kwargs,
            )
        return []

    @cache
    def get_history(
        self,
        item: Movie | Show | Season | Episode,
        min_date: datetime | None = None,
        sort_asc: bool = True,
        **kwargs,
    ) -> list[MovieHistory] | list[EpisodeHistory]:
        """Retrieves watch history for a media item.

        Args:
            item (Movie | Show | Season | Episode): Media item to get history for
            min_date (datetime | None): If provided, only returns history after this date
            sort_asc (bool): Sort order for results
            **kwargs: Additional arguments to pass to fetchItems()

        Returns:
            list[MovieHistory] | list[EpisodeHistory]: Watch history entries for the item

        Note:
            Results are cached using functools.cache decorator
        """
        args = {
            "metadataItemID": item.ratingKey,
            "accountID": self.user_account_id,
            "sort": "viewedAt:asc" if sort_asc else "viewedAt:desc",
        }
        if min_date:
            args["viewedAt>"] = int(min_date.timestamp())

        return self.admin_client.fetchItems(
            f"/status/sessions/history/all{plexapi.utils.joinArgs(args)}", **kwargs
        )

    def get_first_history(
        self, item: Movie | Show | Season | Episode, **kwargs
    ) -> MovieHistory | EpisodeHistory | None:
        """Retrieves the oldest watch history entry for a media item.

        A convenience wrapper around get_history() that returns only the
        first (oldest) history entry.

        Args:
            item (Movie | Show | Season | Episode): Media item to get history for
            **kwargs: Additional arguments to pass to get_history()

        Returns:
            MovieHistory | EpisodeHistory | None: Oldest history entry if found, None if no history exists
        """
        return next(
            iter(self.get_history(item, maxresults=1, sort_asc=True, **kwargs)), None
        )

    def get_last_history(
        self, item: Movie | Show | Season | Episode, **kwargs
    ) -> MovieHistory | EpisodeHistory | None:
        """Retrieves the most recent watch history entry for a media item.

        A convenience wrapper around get_history() that returns only the
        most recent history entry.

        Args:
            item (Movie | Show | Season | Episode): Media item to get history for
            **kwargs: Additional arguments to pass to get_history()

        Returns:
            MovieHistory | EpisodeHistory | None: Most recent history entry if found, None if no history exists
        """
        return next(
            iter(self.get_history(item, maxresults=1, sort_asc=False, **kwargs)), None
        )

    def get_on_deck(
        self,
        item: Show | Season,
        **kwargs,
    ) -> Episode | None:
        """Retrieves the 'On Deck' episode for a show or season.

        Args:
            item (Show | Season): Show or season to check
            **kwargs: Additional arguments to pass to fetchItems()

        Returns:
            Episode | None: Next unwatched episode if found in On Deck, None if no episode is on deck

        Note:
            The On Deck system considers partially watched episodes and
            next episodes in sequence when determining what's on deck
        """
        return next(
            iter(
                self.user_client.fetchItems(
                    f"{item.ratingKey}?includeOnDeck=1",
                    cls=Episode,
                    rtag="OnDeck",
                    **kwargs,
                )
            ),
            None,
        )

    def is_on_watchlist(self, item: Movie | Show) -> bool:
        """Checks if a media item is on the user's watchlist.

        Args:
            item (Movie | Show): Media item to check

        Returns:
            bool: True if item is on watchlist, False otherwise
        """
        return bool(item.onWatchlist()) if self.is_admin_user else False

    def is_on_continue_watching(self, item: Movie | Season, **kwargs) -> bool:
        """Checks if a media item appears in the Continue Watching hub.

        Args:
            item (Movie | Season): Media item to check
            **kwargs: Additional arguments to pass to get_continue_watching()

        Returns:
            bool: True if item appears in Continue Watching hub, False otherwise
        """
        return bool(self.get_continue_watching(item, maxresults=1, **kwargs))

    def is_on_deck(self, item: Movie | Show, **kwargs) -> bool:
        """Checks if a media item has any episodes in the On Deck hub.

        Args:
            item (Movie | Show): Media item to check
            **kwargs: Additional arguments to pass to get_on_deck()

        Returns:
            bool: True if item has any episodes in On Deck hub, False otherwise
        """
        return bool(self.get_on_deck(item, **kwargs))
