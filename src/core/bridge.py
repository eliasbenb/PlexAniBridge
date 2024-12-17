from datetime import datetime
from typing import Optional, Union

from plexapi.library import MovieSection, ShowSection
from sqlmodel import Session

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.models.housekeeping import Housekeeping

from .db import db
from .sync.movie import MovieSyncClient
from .sync.show import ShowSyncClient


class BridgeClient:
    def __init__(
        self,
        # General
        partial_scan: bool,
        destructive_sync: bool,
        # Anilist
        anilist_token: str,
        # Plex
        plex_url: str,
        plex_token: str,
        plex_sections: set[str],
        # Advanced
        dry_run: bool,
        fuzzy_search_threshold: int,
    ) -> None:
        self.partial_scan = partial_scan
        self.destructive_sync = destructive_sync
        self.dry_run = dry_run
        self.fuzzy_search_threshold = fuzzy_search_threshold

        self.anilist_client = AniListClient(anilist_token, dry_run)
        self.animap_client = AniMapClient()
        self.plex_client = PlexClient(plex_url, plex_token, plex_sections)

        sync_client_args = {
            "anilist_client": self.anilist_client,
            "animap_client": self.animap_client,
            "plex_client": self.plex_client,
            "destructive_sync": destructive_sync,
            "fuzzy_search_threshold": fuzzy_search_threshold,
        }
        self.movie_sync = MovieSyncClient(**sync_client_args)
        self.show_sync = ShowSyncClient(**sync_client_args)

        # Get sync state
        self.last_synced = self._get_last_synced()
        self.last_sections_synced = self._get_last_sections_synced()

    def _get_last_synced(self) -> Optional[datetime]:
        with Session(db) as session:
            last_synced = session.get(Housekeeping, "last_synced")
            if last_synced is None or last_synced.value is None:
                return None
            return datetime.fromisoformat(last_synced.value)

    def _set_last_synced(self, last_synced: datetime) -> None:
        with Session(db) as session:
            session.merge(
                Housekeeping(key="last_synced", value=last_synced.isoformat())
            )
            session.commit()

    def _get_last_sections_synced(self) -> set[str]:
        with Session(db) as session:
            last_synced = session.get(Housekeeping, "last_sections_synced")
            if last_synced is None or last_synced.value is None:
                return set()
            return set(last_synced.value.split(","))

    def _set_last_sections_synced(self, last_sections_synced: set[str]) -> None:
        with Session(db) as session:
            session.merge(
                Housekeeping(
                    key="last_sections_synced", value=",".join(last_sections_synced)
                )
            )
            session.commit()

    def _should_perform_partial_scan(self) -> bool:
        return (
            self.partial_scan
            and self.last_synced is not None
            and self.last_sections_synced == self.plex_client.plex_sections
        )

    def sync(self) -> None:
        log.info(
            f"{self.__class__.__name__}: Starting sync between Plex and AniList libraries"
        )

        tmp_last_synced = datetime.now()
        plex_sections = self.plex_client.get_sections()

        for section in plex_sections:
            self._sync_section(section)

        # Update sync state
        self._set_last_synced(tmp_last_synced)
        self._set_last_sections_synced({section.title for section in plex_sections})

        log.info(f"{self.__class__.__name__}: Sync completed successfully")

    def _sync_section(self, section: Union[MovieSection, ShowSection]) -> None:
        log.debug(f"{self.__class__.__name__}: Syncing section '{section.title}'")

        last_synced = self.last_synced if self._should_perform_partial_scan() else None

        if section.type == "movie":
            self.movie_sync.sync_media(section, last_synced)
        elif section.type == "show":
            self.show_sync.sync_media(section, last_synced)
        else:
            log.warning(
                f"{self.__class__.__name__}: Unknown section type for '{section.title}', skipping"
            )
