from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from thefuzz import fuzz

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.models.anilist import AniListMedia, AniListMediaListStatus
from src.models.animap import AniMap

T = TypeVar("T")  # Generic type for media item
S = TypeVar("S")  # Generic type for section


class BaseSyncClient(ABC, Generic[T, S]):
    def __init__(
        self,
        anilist_client: AniListClient,
        animap_client: AniMapClient,
        plex_client: PlexClient,
        destructive_sync: bool,
        fuzzy_search_threshold: int,
    ):
        self.anilist_client = anilist_client
        self.animap_client = animap_client
        self.plex_client = plex_client
        self.destructive_sync = destructive_sync
        self.fuzzy_search_threshold = fuzzy_search_threshold

    def sync_media(self, section: S, last_synced: Optional[datetime] = None) -> None:
        log.debug(
            f"{self.__class__.__name__}: Syncing media in section '{section.title}'"
        )

        media_items = self._get_media_to_sync(section, last_synced)
        log.debug(f"{self.__class__.__name__}: Found {len(media_items)} items to sync")

        for item in media_items:
            self._process_media_item(item)

    @abstractmethod
    def _get_media_to_sync(
        self, section: S, last_synced: Optional[datetime]
    ) -> list[T]:
        pass

    @abstractmethod
    def _process_media_item(self, media_item: T) -> None:
        pass

    def _format_guids(self, guids: list, is_movie: bool = True) -> dict[str, Any]:
        formatted_guids = {
            "tmdb_movie_id": None,
            "tmdb_show_id": None,
            "tvdb_id": None,
            "imdb_id": None,
        }

        for guid in guids:
            if guid.id.startswith("tmdb://"):
                key = "tmdb_movie_id" if is_movie else "tmdb_show_id"
                formatted_guids[key] = int(guid.id.split("://")[1])
            elif guid.id.startswith("tvdb://"):
                formatted_guids["tvdb_id"] = int(guid.id.split("://")[1])
            elif guid.id.startswith("imdb://"):
                formatted_guids["imdb_id"] = guid.id.split("://")[1]

        return formatted_guids

    def _find_anilist_media_by_ids(
        self, title: str, animapping: AniMap
    ) -> Optional[AniListMedia]:
        try:
            if animapping.anilist_id:
                return self.anilist_client.get_anime(animapping.anilist_id[0])
            elif animapping.mal_id:
                log.debug(
                    f"{self.__class__.__name__}: No AniList ID found for '{title}'. "
                    f"Attempting to search AniList for the MAL ID {animapping.mal_id}"
                )
                return self.anilist_client.get_anime(mal_id=animapping.mal_id[0])
        except Exception as e:
            log.error(f"{self.__class__.__name__}: Error finding anime: {e}")
            return None
        return None

    def _search_by_title(
        self, title: str, episode_count: Optional[int] = None
    ) -> Optional[AniListMedia]:
        log.debug(
            f"{self.__class__.__name__}: Attempting to search AniList for title '{title}'"
        )
        search_results = self.anilist_client.search_anime(title)

        for result in search_results:
            if episode_count is not None and result.episodes != episode_count:
                continue

            ratio = fuzz.ratio(title, result.best_title)
            if ratio >= self.fuzzy_search_threshold:
                log.info(
                    f"{self.__class__.__name__}: Matched '{title}' to AniList entry '{result.best_title}' "
                    f"{{anilist_id: {result.id}}} with a ratio of {ratio}"
                )
                return result

        log.warning(
            f"{self.__class__.__name__}: No suitable results found for '{title}' using title search"
        )
        return None

    def _get_anilist_media_data(self, anilist_media: AniListMedia) -> dict:
        if not anilist_media.mediaListEntry:
            return {
                "status": None,
                "score": None,
                "progress": None,
                "repeat": None,
                "notes": None,
                "start_date": None,
                "end_date": None,
            }

        entry = anilist_media.mediaListEntry
        return {
            "status": entry.status,
            "score": entry.score,
            "progress": entry.progress,
            "repeat": entry.repeat,
            "notes": entry.notes,
            "start_date": entry.startedAt,
            "end_date": entry.completedAt,
        }

    def _should_update_status(
        self,
        plex_status: Optional[AniListMediaListStatus],
        anilist_status: Optional[AniListMediaListStatus],
    ) -> bool:
        return plex_status is not None and (
            (anilist_status is not None and plex_status > anilist_status)
            or anilist_status is None
        )

    @abstractmethod
    def _determine_watch_status(
        self, media_item: T
    ) -> Optional[AniListMediaListStatus]:
        pass

    @abstractmethod
    def _sync_media_data(self, media_item: T, anilist_media: AniListMedia) -> None:
        pass

    def _create_sync_update(
        self,
        plex_data: dict,
        anilist_data: dict,
        fields: list[str],
        additional_conditions: dict = None,
    ) -> dict:
        to_sync = {}

        if additional_conditions is None:
            additional_conditions = {}

        for field in fields:
            plex_value = plex_data.get(field)
            anilist_value = anilist_data.get(field)

            if self.destructive_sync is True:
                if plex_value is not None and plex_value != anilist_value:
                    to_sync[field] = plex_value
                continue

            if field == "status" and self._should_update_status(
                plex_value, anilist_value
            ):
                to_sync[field] = plex_value
            elif (
                field == "progress"
                and plex_value is not None
                and plex_value > 0
                and plex_value > (anilist_value or 0)
            ):
                to_sync[field] = plex_value
            elif (
                field == "repeat"
                and plex_value is not None
                and plex_value > (anilist_value or 0)
            ):
                to_sync[field] = plex_value
            elif (
                plex_value is not None
                and plex_value != anilist_value
                and additional_conditions.get(field, True)
            ):
                to_sync[field] = plex_value

        return to_sync
