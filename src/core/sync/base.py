from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Iterator, Optional, TypeVar, Union

from plexapi.media import Guid
from plexapi.video import Movie, Season, Show
from thefuzz import fuzz

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.models.anilist import FuzzyDate, Media, MediaList, MediaListStatus
from src.models.animap import AniMap
from src.settings import SyncField

T = TypeVar("T", bound=Union[Movie, Show])  # Section item
S = TypeVar("S", bound=Union[Movie, Season])  # Item child (season)


@dataclass
class ParsedGuids:
    tvdb: Optional[int] = None
    tmdb: Optional[int] = None
    imdb: Optional[str] = None

    @staticmethod
    def from_guids(guids: list[Guid]) -> "ParsedGuids":
        parsed_guids = ParsedGuids()
        for guid in guids:
            split_guid = guid.id.split("://")
            if len(split_guid) != 2 or not hasattr(parsed_guids, split_guid[0]):
                continue

            try:
                split_guid[1] = int(split_guid[1])
            except ValueError:
                split_guid[1] = str(split_guid[1])

            setattr(parsed_guids, split_guid[0], split_guid[1])
        return parsed_guids

    def __iter__(self) -> Iterator[tuple[str, Optional[Union[int, str]]]]:
        return iter(self.__dict__.items())

    def __str__(self) -> str:
        return ", ".join(f"{k}_id: {v}" for k, v in self if v is not None)


@dataclass
class SyncStats:
    synced: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0

    def __add__(self, other: "SyncStats") -> "SyncStats":
        return SyncStats(
            self.synced + other.synced,
            self.deleted + other.deleted,
            self.skipped + other.skipped,
            self.failed + other.failed,
        )


class BaseSyncClient(ABC, Generic[T, S]):
    def __init__(
        self,
        anilist_client: AniListClient,
        animap_client: AniMapClient,
        plex_client: PlexClient,
        excluded_sync_fields: list[SyncField],
        destructive_sync: bool,
        fuzzy_search_threshold: int,
    ) -> None:
        self.anilist_client = anilist_client
        self.animap_client = animap_client
        self.plex_client = plex_client

        self.excluded_sync_fields = excluded_sync_fields
        self.destructive_sync = destructive_sync
        self.fuzzy_search_threshold = fuzzy_search_threshold

        self.sync_stats = SyncStats()

    def process_media(self, item: T) -> SyncStats:
        guids = ParsedGuids.from_guids(item.guids)
        log.debug(
            f"{self.__class__.__name__}: Processing {item.type} {self._debug_log_title(item)} "
            f"{self._debug_log_ids(item.guid, guids)}"
        )

        for subitem, animapping, guids in self.map_media(item):
            try:
                anilist_media = None
                if animapping and animapping.anilist_id:
                    anilist_media = self.anilist_client.get_anime(animapping.anilist_id)
                    match_method = "mapping lookup"
                elif subitem.type != "season" or subitem.seasonNumber > 0:
                    anilist_media = self.search_media(item, subitem)
                    match_method = "title search"

                if not anilist_media:
                    log.warning(
                        f"{self.__class__.__name__}: No suitable AniList results found during mapping "
                        f"lookup or title search for {item.type} {self._debug_log_title(item, subitem)} "
                        f"{self._debug_log_ids(item.guid, guids)}"
                    )
                    self.sync_stats.failed += 1
                    continue

                animapping = animapping or AniMap(
                    anilist_id=anilist_media.id,
                    tvdb_epoffset=0 if item.type == "show" else None,
                    tvdb_season=subitem.seasonNumber if item.type == "show" else None,
                )

                log.debug(
                    f"{self.__class__.__name__}: Found AniList entry using {match_method} for {item.type} "
                    f"{self._debug_log_title(item, subitem)} "
                    f"{self._debug_log_ids(item.guid, guids, anilist_media.id)}"
                )

                self.sync_media(item, subitem, anilist_media, animapping)
            except Exception as e:
                log.exception(
                    f"{self.__class__.__name__}: Failed to process {item.type} "
                    f"{self._debug_log_title(item, subitem)} "
                    f"{self._debug_log_ids(item.guid, guids)}",
                    exc_info=e,
                )
                self.sync_stats.failed += 1

        return self.sync_stats

    @abstractmethod
    def map_media(self, item: T) -> Iterator[tuple[S, Optional[AniMap]]]:
        pass

    @abstractmethod
    def search_media(self, item: T, subitem: S) -> Optional[Media]:
        pass

    def _best_search_result(self, title: str, results: list[Media]) -> Optional[Media]:
        best_result, best_ratio = max(
            (
                (r, max(fuzz.ratio(title, t) for t in r.title.titles() if t))
                for r in results
                if r.title
            ),
            default=(None, 0),
            key=lambda x: x[1],
        )

        if best_ratio < self.fuzzy_search_threshold:
            return None
        return best_result

    def sync_media(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> SyncStats:
        guids = ParsedGuids.from_guids(item.guids)

        anilist_media_list = (
            anilist_media.media_list_entry if anilist_media.media_list_entry else None
        )
        plex_media_list = self._get_plex_media_list(
            item, subitem, anilist_media, animapping
        )

        if anilist_media_list:
            anilist_media_list.unset_fields(self.excluded_sync_fields)
        plex_media_list.unset_fields(self.excluded_sync_fields)

        final_media_list = self._merge_media_lists(anilist_media_list, plex_media_list)

        if final_media_list == anilist_media_list:
            log.info(
                f"{self.__class__.__name__}: Skipping {item.type} because it is already up to date "
                f"{self._debug_log_title(item, subitem)} "
                f"{self._debug_log_ids(item.guid, guids, anilist_id=animapping.anilist_id)}"
            )
            self.sync_stats.skipped += 1
            return

        if self.destructive_sync and anilist_media_list and not plex_media_list.status:
            log.info(
                f"{self.__class__.__name__}: Deleting AniList entry with variables:"
            )
            log.info(f"\t\t{anilist_media_list}")
            self.anilist_client.delete_anime_entry(
                anilist_media.media_list_entry.id,
                anilist_media.media_list_entry.media_id,
            )
            self.sync_stats.deleted += 1
            return

        if not final_media_list.status:
            log.info(
                f"{self.__class__.__name__}: Skipping {item.type} due to no activity "
                f"{self._debug_log_title(item, subitem)} "
                f"{self._debug_log_ids(item.guid, guids, anilist_id=animapping.anilist_id)}"
            )
            self.sync_stats.skipped += 1
            return

        log.debug(
            f"{self.__class__.__name__}: Syncing AniList entry for {item.type} "
            f"{self._debug_log_title(item, subitem)} "
            f"{self._debug_log_ids(item.guid, guids, anilist_id=animapping.anilist_id)}"
        )
        log.debug(f"\t\tBEFORE => {anilist_media_list}")
        log.debug(f"\t\tAFTER  => {final_media_list}")

        self.anilist_client.update_anime_entry(final_media_list)

        log.info(
            f"{self.__class__.__name__}: Synced {item.type} {self._debug_log_title(item, subitem)} "
            f"{self._debug_log_ids(item.guid, guids, anilist_id=animapping.anilist_id)}"
        )
        self.sync_stats.synced += 1

    def _get_plex_media_list(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> MediaList:
        media_list = MediaList(
            id=anilist_media.media_list_entry
            and anilist_media.media_list_entry.id
            or 0,
            user_id=self.anilist_client.user.id,
            media_id=anilist_media.id,
            status=self._calculate_status(item, subitem, anilist_media, animapping),
            score=self._calculate_score(item, subitem, anilist_media, animapping),
            progress=self._calculate_progress(item, subitem, anilist_media, animapping),
            repeat=self._calculate_repeats(item, subitem, anilist_media, animapping),
        )

        if media_list.status is None:
            return media_list

        if "notes" not in self.excluded_sync_fields:
            media_list.notes = self.plex_client.get_user_review(
                subitem
            ) or self.plex_client.get_user_review(item)

        if media_list.status > MediaListStatus.PLANNING:
            media_list.started_at = self._calculate_started_at(
                item, subitem, anilist_media, animapping
            )
        if media_list.status >= MediaListStatus.COMPLETED:
            media_list.completed_at = self._calculate_completed_at(
                item, subitem, anilist_media, animapping
            )

        return media_list

    @abstractmethod
    def _calculate_status(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> Optional[MediaListStatus]:
        pass

    @abstractmethod
    def _calculate_score(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> Optional[int]:
        pass

    @abstractmethod
    def _calculate_progress(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> Optional[int]:
        pass

    @abstractmethod
    def _calculate_repeats(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> Optional[int]:
        pass

    @abstractmethod
    def _calculate_started_at(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> Optional[FuzzyDate]:
        pass

    @abstractmethod
    def _calculate_completed_at(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> Optional[FuzzyDate]:
        pass

    def _merge_media_lists(
        self,
        anilist_media_list: Optional[MediaList],
        plex_media_list: MediaList,
    ) -> MediaList:
        if not anilist_media_list:
            return plex_media_list.model_copy()
        res_media_list = anilist_media_list.model_copy()

        COMPARISON_RULES = {
            "score": "ne",
            "notes": "ne",
            "progress": "gt",
            "repeat": "gt",
            "status": "gte",
            "started_at": "lt",
            "completed_at": "lt",
        }

        def should_update(op: str, p_val, a_val) -> bool:
            if p_val is None:
                return False
            match op:
                case "ne":
                    return p_val != a_val
                case "gt":
                    return self.destructive_sync or p_val > a_val
                case "gte":
                    return self.destructive_sync or p_val >= a_val
                case "lt":
                    return self.destructive_sync or p_val < a_val
                case "lte":
                    return self.destructive_sync or p_val <= a_val
            return False

        for key, rule in COMPARISON_RULES.items():
            plex_val = getattr(plex_media_list, key)
            anilist_val = getattr(anilist_media_list, key)
            if should_update(rule, plex_val, anilist_val):
                setattr(res_media_list, key, plex_val)

        return res_media_list

    def _debug_log_title(self, item: T, subitem: Optional[S] = None) -> str:
        if subitem and item != subitem:
            return f"$$'{item.title} | {subitem.title}'$$"
        return f"$$'{item.title}'$$"

    def _debug_log_ids(
        self,
        plex_id: str,
        guids: ParsedGuids,
        anilist_id: Optional[int] = None,
    ) -> str:
        return f"$${{plex_id: {plex_id}, {guids}{f', anilist_id: {anilist_id}' if anilist_id else ''}}}$$"
