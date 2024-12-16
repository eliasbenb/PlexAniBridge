from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Union

import requests
from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.video import Episode, Movie, Season, Show

from src import log


@dataclass(frozen=True)
class ReviewKey:
    """Immutable class for creating cache keys for reviews."""

    rating_key: str
    item_type: str
    guid: str


class PlexClient:
    def __init__(self, plex_url: str, plex_token: str, plex_sections: list[str]):
        self.plex_url = plex_url
        self.plex_token = plex_token
        self.plex_sections = plex_sections

        self.client = PlexServer(self.plex_url, self.plex_token)
        self.__validate_sections()
        self.on_deck_window = self.__get_on_deck_window()

        self._get_user_review_cached = lru_cache(maxsize=32)(self._get_user_review)

    def __validate_sections(self) -> None:
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

    def __get_on_deck_window(self) -> int:
        return self.client.settings.get("OnDeckWindow").value

    def get_section(self, section_name: str) -> Union[MovieSection, ShowSection]:
        log.debug(f"{self.__class__.__name__}: Getting section '{section_name}'")
        section = self.client.library.section(section_name)
        if section.title not in self.plex_sections:
            raise ValueError(
                f"Section '{section_name}' was not set in the `PLEX_SECTIONS` config"
            )
        return section

    def get_sections(self) -> Union[list[MovieSection], list[ShowSection]]:
        log.debug(f"{self.__class__.__name__}: Getting all sections")
        return [
            section
            for section in self.client.library.sections()
            if section.title in self.plex_sections
        ]

    def get_section_items(self, section_name: str) -> Union[list[Movie], list[Show]]:
        log.debug(
            f"{self.__class__.__name__}: Getting items from section '{section_name}'"
        )
        section = self.get_section(section_name)
        return section.all()

    def get_user_review(self, item: Union[Movie, Show, Season]) -> Optional[str]:
        if item.type not in ("movie", "show"):
            return None

        cache_key = ReviewKey(
            rating_key=str(item.ratingKey), item_type=item.type, guid=item.guid
        )

        return self._get_user_review_cached(cache_key)

    def _get_user_review(self, cache_key: ReviewKey) -> Optional[str]:
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
            f"{self.__class__.__name__}: Getting reviews for item with Plex GUID '{guid}'"
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
        return self.client.library.onDeck(item) is not None
