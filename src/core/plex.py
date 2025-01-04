from datetime import datetime
from functools import cache
from textwrap import dedent

import plexapi.utils
import requests
from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.video import Episode, EpisodeHistory, Movie, MovieHistory, Season, Show

from src import log


class PlexClient:
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

    def _init_user_client(self) -> PlexServer:
        """Get the Plex client for the user account

        It handles cases where the user account is an admin user, regular user, or home user.

        Returns:
            PlexServer: The Plex client for the user account
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

    def get_sections(self) -> list[MovieSection] | list[ShowSection]:
        """Get all Plex sections that are configured

        Returns:
            list[MovieSection] | list[ShowSection]: List of configured Plex sections
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
        """Get all items in a Plex section

        Args:
            section (MovieSection | ShowSection): The target section
            min_last_modified (datetime | None): The minimum last update, view, or rating time. Defaults to None.

        Returns:
            list[Movie] | list[Show]: List of items in the section
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
        """Get the user review for a movie or show

        Args:
            item (Movie | Show | Season): The target item

        Returns:
            str | None: The user review or None if not found
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
        """Filter episodes based on the start and end episode numbers

        Args:
            season: The season to filter
            start: The start episode number
            end: The end episode number
        Returns:
            list[Episode]: List of filtered episodes
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
        """Filter episodes based on the start and end episode numbers that have been watched

        Args:
            season: The season to filter
            start: The start episode number
            end: The end episode number

        Returns:
            list[Episode]: List of filtered episodes
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
        """Get the items that are in the 'Continue Watching' hub for a movie or season

        Args:
            item (Movie | Season): The target item

        Returns:
            list[Movie] | list[Episode]: The item(s) related to the target item that are in the 'Continue Watching' hub
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
        """Get the history for a movie, show, or season

        Args:
            item (Movie | Show | Season): The target item
            min_date (datetime | None): The minimum date to include in the history. Defaults to None.
            max_results (int | None): The maximum number of results to return. Defaults to None.
            sort_asc (bool | None): Sort the history in ascending order. Defaults to True.

        Returns:
                list[MovieHistory] | list[EpisodeHistory]: The history for the target item
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
        """Get the first (oldest) history for a movie, show, or season

        Args:
            item (Movie | Show | Season | Episode): The target item

        Returns:
            MovieHistory | EpisodeHistory | None: The first (oldest) history for the target item
        """
        return next(
            iter(self.get_history(item, maxresults=1, sort_asc=True, **kwargs)), None
        )

    def get_last_history(
        self, item: Movie | Show | Season | Episode, **kwargs
    ) -> MovieHistory | EpisodeHistory | None:
        """Get the last (most recent) history for a movie, show, or season
        Args:
            item (Movie | Show | Season | Episode): The target item

        Returns:
            MovieHistory | EpisodeHistory | None: The last (most recent) history for the target item
        """
        return next(
            iter(self.get_history(item, maxresults=1, sort_asc=False, **kwargs)), None
        )

    def get_on_deck(
        self,
        item: Show | Season,
        **kwargs,
    ) -> Episode | None:
        """Get the items that are in the 'On Deck' hub for a movie or season

        Args:
            item (Show | Season): The target item

        Returns:
                Episode | None: The item that's on deck
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
        """Check if a movie or show is on the user's watchlist

        Args:
            item (Movie | Show): The target item

        Returns:
            bool: True if the item is on the watchlist, False otherwise
        """
        return bool(item.onWatchlist()) if self.is_admin_user else False

    def is_on_continue_watching(self, item: Movie | Season, **kwargs) -> bool:
        """Check if a movie or season is on the 'Continue Watching' hub

        Args:
            item (Movie | Season): The target item

        Returns:
            bool: True if the item is on the 'Continue Watching' hub, False otherwise
        """
        return bool(self.get_continue_watching(item, maxresults=1, **kwargs))

    def is_on_deck(self, item: Movie | Show, **kwargs) -> bool:
        """Check if a movie or show is on the 'On Deck' hub

        Args:
            item (Movie | Show): The target item

        Returns:
            bool: True if the item is on the 'On Deck' hub, False otherwise
        """
        return bool(self.get_on_deck(item, **kwargs))
