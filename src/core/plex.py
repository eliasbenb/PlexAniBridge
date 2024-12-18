from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Optional, Union

import requests
from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.video import Episode, Movie, Season, Show

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

        self._get_user_review_cached = lru_cache(maxsize=32)(self._get_user_review)

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
                    f"Section '{section_name}' was not found in the Plex server"
                )

            if section.type not in ["movie", "show"]:
                raise ValueError(
                    f"Section '{section_name}' is not a movie or show section"
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
        filters = {}
        if min_last_modified:
            log.debug(
                f"{self.__class__.__name__}: `PARTIAL_SCAN` is set. Filtering '{section.title}' "
                f"by items last updated, viewed, or rated after {min_last_modified}"
            )
            filters |= {
                "or": [
                    {"updatedAt>>=": min_last_modified},
                    {"lastViewedAt>>=": min_last_modified},
                    {"lastRatedAt>>=": min_last_modified},
                ]
            }
        if require_watched:
            log.debug(
                f"{self.__class__.__name__}: Filtering '{section.title}' by items that have been watched"
            )
            filters |= {"viewCount>>=": 0}

        return section.search(filters=filters)

    def get_user_review(self, item: Union[Movie, Show, Season]) -> Optional[str]:
        """Get the user review for a movie or show

        Args:
            item (Union[Movie, Show, Season]): The target item

        Returns:
            Optional[str]: The user review or None if not found
        """
        if item.type not in ("movie", "show"):
            return None

        # To avoid making multiple requests for the same item, we cache the responses in an LRU cache
        cache_key = ReviewKey(
            rating_key=str(item.ratingKey),
            item_type=item.type,
            title=item.title,
            guid=item.guid,
        )

        # We use the cached version if it exists or otherwise call `_get_user_review()`
        return self._get_user_review_cached(cache_key)

    def _get_user_review(self, cache_key: ReviewKey) -> Optional[str]:
        """Get the user review for a movie or show cachelessly

        Args:
            cache_key (ReviewKey): The unique key to cache the response

        Returns:
            Optional[str]: The user review or None if not found
        """
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

        if cache_key.item_type == "movie":
            guid = cache_key.guid[13:]
        else:
            guid = cache_key.guid[12:]

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Plex-Token": self.plex_token,
        }

        log.debug(
            f"{self.__class__.__name__}: Getting reviews for '{cache_key.title}' {{plex_id: {cache_key.guid}}}"
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
                f"Failed to get review for item with rating key '{cache_key.rating_key}'",
                exc_info=e,
            )
            return None
        except (KeyError, ValueError) as e:
            log.error(
                f"Failed to parse review response for item with rating key '{cache_key.rating_key}'",
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

    def is_on_deck(self, item: Union[Movie, Show]) -> bool:
        """Check if a movie or show is on the 'On Deck' hub

        Args:
            item (Union[Movie, Show]): The target item

        Returns:
            bool: True if the item is on the 'On Deck' hub, False otherwise
        """
        return self.client.library.onDeck(item) is not None
