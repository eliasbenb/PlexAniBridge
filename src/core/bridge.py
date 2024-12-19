from datetime import datetime
from typing import Optional, Union

from plexapi.library import MovieSection, ShowSection
from sqlmodel import Session

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.models.housekeeping import Housekeeping
from src.settings import Config

from .db import db
from .sync.movie import MovieSyncClient
from .sync.show import ShowSyncClient


class BridgeClient:
    """The main client that orchestrates the sync between Plex and AniList libraries

    All components of the program are managed and initialized by this class.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

        self.anilist_client = AniListClient(config.ANILIST_TOKEN, config.DRY_RUN)
        self.animap_client = AniMapClient()
        self.plex_client = PlexClient(
            config.PLEX_URL, config.PLEX_TOKEN, config.PLEX_SECTIONS
        )

        sync_client_args = {
            "anilist_client": self.anilist_client,
            "animap_client": self.animap_client,
            "plex_client": self.plex_client,
            "destructive_sync": config.DESTRUCTIVE_SYNC,
            "fuzzy_search_threshold": config.FUZZY_SEARCH_THRESHOLD,
        }
        self.movie_sync = MovieSyncClient(**sync_client_args)
        self.show_sync = ShowSyncClient(**sync_client_args)

        self.last_synced = self._get_last_synced()
        self.last_sections_synced = self._get_last_sections_synced()

    def _get_last_synced(self) -> Optional[datetime]:
        """Get the timestamp of the last sync

        Returns:
            Optional[datetime]: The timestamp of the last sync, or None if it has never been synced
        """
        with Session(db) as session:
            last_synced = session.get(Housekeeping, "last_synced")
            if last_synced is None or last_synced.value is None:
                return None
            return datetime.fromisoformat(last_synced.value)

    def _set_last_synced(self, last_synced: datetime) -> None:
        """Store the timestamp of the last sync

        Args:
            last_synced (datetime): The timestamp of the last sync
        """
        with Session(db) as session:
            session.merge(
                Housekeeping(key="last_synced", value=last_synced.isoformat())
            )
            session.commit()

    def _get_last_sections_synced(self) -> set[str]:
        """Get the configured Plex sections that were last synced

        If the sections have been changed since the last sync, a full scan will need to be performed (ignoring the `PARTIAL_SCAN` setting)

        Returns:
            set[str]: The set of Plex section titles that were last synced
        """
        with Session(db) as session:
            last_synced = session.get(Housekeeping, "last_sections_synced")
            if last_synced is None:
                return set()
            return set(last_synced.value.split(","))

    def _set_last_sections_synced(self, last_sections_synced: set[str]) -> None:
        """Store the configured Plex sections that were last synced

        Args:
            last_sections_synced (set[str]): The set of Plex section titles that were last synced
        """
        with Session(db) as session:
            session.merge(
                Housekeeping(
                    key="last_sections_synced", value=",".join(last_sections_synced)
                )
            )
            session.commit()

    def sync(self) -> None:
        """Sync the Plex and AniList libraries"""
        log.info(
            f"{self.__class__.__name__}: Starting "
            f"{'partial ' if self.config.PARTIAL_SCAN else ''}"
            f"{'and ' if self.config.PARTIAL_SCAN and self.config.DESTRUCTIVE_SYNC else ''}"
            f"{'destructive ' if self.config.DESTRUCTIVE_SYNC else ''}"
            f"sync between Plex and AniList libraries"
        )

        tmp_last_synced = datetime.now()  # We'll store this if the sync is successful
        plex_sections = self.plex_client.get_sections()

        for section in plex_sections:
            self._sync_section(section)

        # Update the sync state
        self._set_last_synced(tmp_last_synced)
        self._set_last_sections_synced({section.title for section in plex_sections})

        log.info(
            f"{self.__class__.__name__}: Anime mappings sync completed successfully"
        )

    def _sync_section(self, section: Union[MovieSection, ShowSection]) -> None:
        """Sync a Plex section with the AniList library

        Args:
            section (Union[MovieSection, ShowSection]): The Plex section to sync
        """
        log.debug(f"{self.__class__.__name__}: Syncing section '{section.title}'")

        items = self.plex_client.get_section_items(
            section,
            min_last_modified=self.last_synced
            if self._should_perform_partial_scan()
            else None,
            require_watched=True,
        )

        if section.type == "movie":
            for item in items:
                self.movie_sync.process_media(item)
        elif section.type == "show":
            for item in items:
                self.show_sync.process_media(item)

    def _should_perform_partial_scan(self) -> bool:
        """Check if a partial scan can be performed

        A partial scan can only be performed if the following conditions are met:
            1. The `PARTIAL_SCAN` setting is enabled
            2. The last sync timestamp is not None
            3. The last synced sections match the configured Plex sections

        Returns:
            bool: True if a partial scan can be performed, False otherwise
        """
        return (
            self.config.PARTIAL_SCAN
            and self.last_synced is not None
            and self.last_sections_synced == self.plex_client.plex_sections
        )
