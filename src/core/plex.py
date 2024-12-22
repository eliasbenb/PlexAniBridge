from datetime import datetime
from functools import cache
from typing import Optional, Union

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

        It handles cases where the user account is an admin or a regular user.

        Returns:
            PlexServer: The Plex client for the user account
        """
        admin_account = self.admin_client.myPlexAccount()
        self.is_admin_user = admin_account.username == self.plex_user

        if self.is_admin_user:
            self.user_client = self.admin_client
            self.user_account_id = 1
        else:
            self.user_client = self.admin_client.switchUser(self.plex_user)
            self.user_account_id = next(
                u.id for u in admin_account.users() if u.username == self.plex_user
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

    def get_sections(self) -> Union[list[MovieSection], list[ShowSection]]:
        """Get all Plex sections that are configured

        Returns:
            Union[list[MovieSection], list[ShowSection]]: List of configured Plex sections
        """
        log.debug(f"{self.__class__.__name__}: Getting all sections")

        return [
            section
            for section in self.user_client.library.sections()
            if section.title in self.plex_sections
        ]

    def get_section_items(
        self,
        section: Union[MovieSection, ShowSection],
        min_last_modified: Optional[datetime] = None,
        require_watched: bool = False,
    ) -> list[Union[Movie, Show]]:
        """Get all items in a Plex section

        Args:
            section (Union[MovieSection, ShowSection]): The target section
            min_last_modified (Optional[datetime], optional): The minimum last update, view, or rating time. Defaults to None.

        Returns:
            list[Union[Movie, Show]]: List of items in the section
        """
        filters = {"and": []}
        if min_last_modified:
            log.debug(
                f"{self.__class__.__name__}: `PARTIAL_SCAN` is set. Filtering section $$'{section.title}'$$ "
                f"by items last updated, viewed, or rated after {
                    min_last_modified}"
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
                f"{self.__class__.__name__}: Filtering section '{
                    section.title}' by items that have been watched"
            )

        return section.search(filters=filters)

    @cache
    def get_user_review(self, item: Union[Movie, Show, Season]) -> Optional[str]:
        """Get the user review for a movie or show

        Args:
            item (Union[Movie, Show, Season]): The target item

        Returns:
            Optional[str]: The user review or None if not found
        """
        if not self.is_admin_user:
            return None

        if item.type not in ("movie", "show", "season"):
            return None

        query = """
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
        """

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
                f"Failed to get review for {item.type} $$'{item.title}&#0146 "
                f"{{plex_key: {item.ratingKey}}}",
                exc_info=e,
            )
            return None
        except (KeyError, ValueError) as e:
            log.error(
                f"Failed to parse review for {item.type} $$'{item.title}&#0146 "
                f"{{plex_key: {item.ratingKey}}}",
                exc_info=e,
            )
            return None

    def get_continue_watching(
        self,
        item: Union[Movie, Season],
        **kwargs,
    ) -> Union[list[Movie], list[Episode]]:
        """Get the items that are in the 'Continue Watching' hub for a movie or season

        Args:
            item (Union[Movie, Season]): The target item

        Returns:
            Union[list[Movie], list[Episode]]: The item(s) related to the target item that are in the 'Continue Watching' hub
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
        item: Union[Movie, Show, Season, Episode],
        min_date: Optional[datetime] = None,
        sort_asc: bool = True,
        **kwargs,
    ) -> Union[list[MovieHistory], list[EpisodeHistory]]:
        """Get the history for a movie, show, or season

        Args:
            item (Union[Movie, Show, Season]): The target item
            min_date (Optional[datetime], optional): The minimum date to include in the history. Defaults to None.
            max_results (Optional[int], optional): The maximum number of results to return. Defaults to None.
            sort_asc (bool, optional): Sort the history in ascending order. Defaults to True.

        Returns:
                Union[list[MovieHistory], list[EpisodeHistory]]: The history for the target item
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
        self, item: Union[Movie, Show, Season, Episode], **kwargs
    ) -> Optional[Union[MovieHistory, EpisodeHistory]]:
        """Get the first (oldest) history for a movie, show, or season

        Args:
            item (Union[Movie, Show, Season, Episode]): The target item

        Returns:
            Optional[Union[MovieHistory, EpisodeHistory]]: The first (oldest) history for the target item
        """
        return next(
            iter(self.get_history(item, maxresults=1, sort_asc=True, **kwargs)), None
        )

    def get_last_history(
        self, item: Union[Movie, Show, Season, Episode], **kwargs
    ) -> Optional[Union[MovieHistory, EpisodeHistory]]:
        """Get the last (most recent) history for a movie, show, or season
        Args:
            item (Union[Movie, Show, Season, Episode]): The target item

        Returns:
            Optional[Union[MovieHistory, EpisodeHistory]]: The last (most recent) history for the target item
        """
        return next(
            iter(self.get_history(item, maxresults=1, sort_asc=False, **kwargs)), None
        )

    def get_on_deck(
        self,
        item: Union[Show, Season],
        **kwargs,
    ) -> Optional[Episode]:
        """Get the items that are in the 'On Deck' hub for a movie or season

        Args:
            item (Union[Show, Season]): The target item

        Returns:
                Optional[Episode]: The item that's on deck
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

    def is_on_watchlist(self, item: Union[Movie, Show]) -> bool:
        """Check if a movie or show is on the user's watchlist

        Args:
            item (Union[Movie, Show]): The target item

        Returns:
            bool: True if the item is on the watchlist, False otherwise
        """
        return bool(item.onWatchlist()) if self.is_admin_user else False

    def is_on_continue_watching(self, item: Union[Movie, Season], **kwargs) -> bool:
        """Check if a movie or season is on the 'Continue Watching' hub

        Args:
            item (Union[Movie, Episode]): The target item

        Returns:
            bool: True if the item is on the 'Continue Watching' hub, False otherwise
        """
        return bool(self.get_continue_watching(item, maxresults=1, **kwargs))

    def is_on_deck(self, item: Union[Movie, Show], **kwargs) -> bool:
        """Check if a movie or show is on the 'On Deck' hub

        Args:
            item (Union[Movie, Show]): The target item

        Returns:
            bool: True if the item is on the 'On Deck' hub, False otherwise
        """
        return bool(self.get_on_deck(item, **kwargs))
