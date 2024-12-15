from typing import Union

from plexapi.library import MovieSection, ShowSection
from plexapi.server import PlexServer
from plexapi.video import Movie, Show

from src import log


class PlexClient:
    def __init__(
        self, plex_url: str, plex_token: str, plex_sections: list[str], plex_user: str
    ):
        self.plex_url = plex_url
        self.plex_token = plex_token
        self.plex_sections = plex_sections
        self.plex_user = plex_user

        self.client = PlexServer(self.plex_url, self.plex_token)
        self.__validate_sections()

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

    def is_movie(self, item: Union[Movie, Show]) -> bool:
        return isinstance(item, (Movie, MovieSection))

    def is_show(self, item: Union[Movie, Show]) -> bool:
        return isinstance(item, (Show, ShowSection))