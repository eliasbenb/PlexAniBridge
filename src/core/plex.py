from typing import Optional, Union

import requests
from plexapi import BASE_HEADERS
from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.video import Movie, Show

from src import log


class PlexClient:
    def __init__(self, plex_url: str, plex_token: str, plex_sections: list[str]):
        self.plex_url = plex_url
        self.plex_token = plex_token
        self.plex_sections = plex_sections

        self.client = PlexServer(self.plex_url, self.plex_token)
        self.__validate_sections()
        self.weeks_to_consider_continue_watching = self.__get_on_deck_window()

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
        return self.client.settings.get("OnDeckWindow")

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

    def get_user_review(self, item: Union[Movie, Show]) -> Optional[str]:
        log.debug(f"{self.__class__.__name__}: Getting reviews for item '{item.title}'")

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

        if item.type == "movie":
            guid = item.guid[13:]
        elif item.type == "show":
            guid = item.guid[12:]
        else:
            return

        headers = BASE_HEADERS.copy()
        headers["X-Plex-Token"] = self.plex_token

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

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            log.error(f"Failed to get review for item '{item.title}'", exc_info=e)
            return None

        data = response.json()["data"]["metadataReviewV2"]

        if not data or "message" not in data:
            return None
        return data["message"]

    def is_movie(self, item: Union[Movie, Show]) -> bool:
        return isinstance(item, (Movie, MovieSection))

    def is_show(self, item: Union[Movie, Show]) -> bool:
        return isinstance(item, (Show, ShowSection))
