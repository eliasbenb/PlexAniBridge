from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Optional, Union

import requests
from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.utils import joinArgs
from plexapi.video import Episode, EpisodeHistory, Movie, MovieHistory, Season, Show

from src import log


@dataclass(frozen=True)
class ReviewKey:
    """Key used to cache API responses for user reviews"""

    rating_key: str
    item_type: str
    title: str
    guid: str


class PlexClient:
    def __init__(
        self, plex_url: str, plex_token: str, plex_sections: list[str]
    ) -> None:
        self.plex_url = plex_url
        self.plex_token = plex_token
        self.plex_sections = plex_sections

        self.client = PlexServer(self.plex_url, self.plex_token)
        self.__validate_sections()

    def __validate_sections(self) -> None:
        """Does basic validation of the configured Plex sections

        The function checks if the configured sections:
            1. Exist in the Plex server
            2. Are of type 'movie' or 'show'

        Raises:
            ValueError: If any of the sections are invalid
        """
        log.debug(f"{self.__class__.__name__}: Validating configured sections")

        sections = self.client.library.sections()
        section_name_map = {section.title: section for section in sections}

        for section_name in self.plex_sections:
            try:
                section = section_name_map[section_name]
            except KeyError:
                raise ValueError(
                    f"Section \u2018{section_name}\u2019 was not found in the Plex server"
                )

            if section.type not in ["movie", "show"]:
                raise ValueError(
                    f"Section \u2018{section_name}\u2019 is not a movie or show section"
                )

        log.debug(f"{self.__class__.__name__}: All sections are valid")

    def get_sections(self) -> Union[list[MovieSection], list[ShowSection]]:
        """Get all Plex sections that are configured

        Returns:
            Union[list[MovieSection], list[ShowSection]]: List of configured Plex sections
        """
        log.debug(f"{self.__class__.__name__}: Getting all sections")

        return [
            section
            for section in self.client.library.sections()
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
                f"{self.__class__.__name__}: `PARTIAL_SCAN` is set. Filtering section \u2018{section.title}\u2019 "
                f"by items last updated, viewed, or rated after {
                    min_last_modified}"
            )
            filters["and"].append(
                {
                    "or": [
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
            filters["and"].append({"viewCount>>=": 0})

        return section.search(filters=filters)

    @cache
    def get_user_review(self, item: Union[Movie, Show, Season]) -> Optional[str]:
        """Get the user review for a movie or show

        Args:
            item (Union[Movie, Show, Season]): The target item

        Returns:
            Optional[str]: The user review or None if not found
        """
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
            f"\u2018{item.title}\u2019 {{plex_id: {item.guid}}}"
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
                f"Failed to get review for {item.type} \u2018{item.title}&#0146 "
                f"{{plex_key: {item.ratingKey}}}",
                exc_info=e,
            )
            return None
        except (KeyError, ValueError) as e:
            log.error(
                f"Failed to parse review for {item.type} \u2018{item.title}&#0146 "
                f"{{plex_key: {item.ratingKey}}}",
                exc_info=e,
            )
            return None

    def get_continue_watching(
        self, item: Union[Movie, Season]
    ) -> Union[list[Movie], list[Episode]]:
        """Get the items that are in the 'Continue Watching' hub for a movie or season

        Args:
            item (Union[Movie, Season]): The target item

        Returns:
            Union[list[Movie], list[Episode]]: The item(s) related to the target item that are in the 'Continue Watching' hub
        """
        if item.type == "movie":
            return self.client.fetchItems(
                "/hubs/continueWatching/items", ratingKey=item.ratingKey
            )
        elif item.type == "season":
            return self.client.fetchItems(
                "/hubs/continueWatching/items", parentRatingKey=item.ratingKey
            )
        else:
            return []

    @cache
    def get_history(
        self,
        item: Union[Movie, Show, Season],
        min_date: Optional[datetime] = None,
        max_results: Optional[int] = None,
        sort_asc: bool = True,
    ) -> Union[MovieHistory, EpisodeHistory]:
        """Get the history for a movie, show, or season

        Args:
            item (Union[Movie, Show, Season]): The target item
            min_date (Optional[datetime], optional): The minimum date to include in the history. Defaults to None.
            max_results (Optional[int], optional): The maximum number of results to return. Defaults to None.
            sort_asc (bool, optional): Sort the history in ascending order. Defaults to True.

        Returns:
                list[PlexHistory]: The history for the target item
        """
        args = {
            "metadataItemID": item.ratingKey,
            "sort": f"viewedAt:{'asc' if sort_asc else 'desc'}",
        }
        if min_date:
            args["viewedAt>"] = int(min_date.timestamp())

        key = f"/status/sessions/history/all{joinArgs(args)}"
        return self.client.fetchItems(key, maxresults=max_results)

    def is_on_deck(self, item: Union[Movie, Show]) -> bool:
        """Check if a movie or show is on the 'On Deck' hub

        Args:
            item (Union[Movie, Show]): The target item

        Returns:
            bool: True if the item is on the 'On Deck' hub, False otherwise
        """
        return self.client.library.onDeck(item) is not None
