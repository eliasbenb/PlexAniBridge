from abc import ABC, abstractmethod
from typing import Generic, Iterator, TypeVar

from plexapi.media import Guid
from plexapi.video import Episode, Movie, Season, Show
from thefuzz import fuzz

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.models.anilist import FuzzyDate, Media, MediaList, MediaListStatus, ScoreFormat
from src.models.animap import AniMap
from src.settings import SyncField
from pydantic import BaseModel

T = TypeVar("T", bound=Movie | Show)  # Section item
S = TypeVar("S", bound=Movie | Season)  # Item child (season)
E = TypeVar("E", bound=Movie | Episode)  # Item grandchild (episode)


class ParsedGuids(BaseModel):
    """Container for parsed media identifiers from different services.

    Handles parsing and storage of media IDs from various services (TVDB, TMDB, IMDB)
    from Plex's GUID format into a structured format. Provides iteration and string
    representation for debugging.

    Attributes:
        tvdb (int | None): TVDB ID if available
        tmdb (int | None): TMDB ID if available
        imdb (str | None): IMDB ID if available

    Note:
        GUID formats expected from Plex:
        - TVDB: "tvdb://123456"
        - TMDB: "tmdb://123456"
        - IMDB: "imdb://tt1234567"
    """

    tvdb: int | None = None
    tmdb: int | None = None
    imdb: str | None = None

    @staticmethod
    def from_guids(guids: list[Guid]) -> "ParsedGuids":
        """Creates a ParsedGuids instance from a list of Plex GUIDs.

        Args:
            guids (list[Guid]): List of Plex GUID objects

        Returns:
            ParsedGuids: New instance with parsed IDs
        """
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

    def __str__(self) -> str:
        """Creates a string representation of the parsed IDs.

        Returns:
            str: String representation of the parsed IDs in a format like "id: xxx, id: xxx, id: xxx"
        """
        return ", ".join(
            f"{field}: {getattr(self, field)}"
            for field in self.model_fields
            if getattr(self, field) is not None
        )

    def __iter__(self) -> Iterator[tuple[str, int | str | None]]:
        """Enables iteration over non-None GUIDs.

        Returns:
            Iterator[tuple[str, int | str | None]]: Iterator of (service, id) pairs
        """
        return iter(self.model_dump(exclude_none=True).items())


class SyncStats(BaseModel, arbitrary_types_allowed=True):
    """Statistics tracker for synchronization operations.

    Keeps count of various sync outcomes for reporting and monitoring.

    Attributes:
        synced (int): Number of successfully synced items
        deleted (int): Number of items deleted from AniList
        skipped (int): Number of items that needed no changes
        failed (int): Number of items that failed to sync

    Note:
        Supports addition via the + operator for combining stats
        from multiple operations
    """

    synced: int = 0
    deleted: int = 0
    skipped: int = 0
    not_found: int = 0
    failed: int = 0

    possible: set[E] = set()
    covered: set[E] = set()

    @property
    def coverage(self) -> float:
        """Calculates the coverage percentage of successfully synced items.

        Returns:
            float: Coverage percentage of successfully synced items
        """
        return len(self.covered) / len(self.possible) if self.possible else 0.0

    def __add__(self, other: "SyncStats") -> "SyncStats":
        return SyncStats(
            synced=self.synced + other.synced,
            deleted=self.deleted + other.deleted,
            skipped=self.skipped + other.skipped,
            not_found=self.not_found + other.not_found,
            failed=self.failed + other.failed,
            possible=self.possible.union(other.possible),
            covered=self.covered.union(other.covered),
        )


class BaseSyncClient(ABC, Generic[T, S, E]):
    """Abstract base class for media synchronization between Plex and AniList.

    Provides core synchronization logic while allowing specialized implementations
    for different media types through abstract methods.

    Type Parameters:
        T: Main media type (Movie or Show)
        S: Child item type (Movie or Season)
        E: Grandchild item type (Movie or Episode)
    """

    def __init__(
        self,
        anilist_client: AniListClient,
        animap_client: AniMapClient,
        plex_client: PlexClient,
        excluded_sync_fields: list[SyncField],
        full_scan: bool,
        destructive_sync: bool,
        fuzzy_search_threshold: int,
    ) -> None:
        """Initializes a new synchronization client.

        Args:
            anilist_client (AniListClient): AniList API client
            animap_client (AniMapClient): AniMap API client
            plex_client (PlexClient): Plex API client
            excluded_sync_fields (list[SyncField]): Fields to exclude from synchronization
            destructive_sync (bool): Whether to delete AniList entries not found in Plex
            fuzzy_search_threshold (int): Minimum match ratio for fuzzy title
        """
        self.anilist_client = anilist_client
        self.animap_client = animap_client
        self.plex_client = plex_client

        self.excluded_sync_fields = excluded_sync_fields
        self.full_scan = full_scan
        self.destructive_sync = destructive_sync
        self.fuzzy_search_threshold = fuzzy_search_threshold

        self.sync_stats = SyncStats()

    def clear_cache(self) -> None:
        """Clears the cache for all decorated methods in the class."""
        for attr in dir(self):
            if callable(getattr(self, attr)) and hasattr(
                getattr(self, attr), "cache_clear"
            ):
                getattr(self, attr).cache_clear()

    def process_media(self, item: T) -> SyncStats:
        """Processes a single media item for synchronization.

        Args:
            item (T): Grandparent Plex media item to sync

        Returns:
            SyncStats: Updated synchronization statistics with counts of synced, deleted, skipped and failed items
        """
        guids = ParsedGuids.from_guids(item.guids)

        debug_log_title = self._debug_log_title(item=item)
        debug_log_ids = self._debug_log_ids(
            key=item.ratingKey, plex_id=item.guid, guids=guids
        )

        log.debug(
            f"{self.__class__.__name__}: Processing {item.type} "
            f"{debug_log_title} {debug_log_ids}"
        )

        for child_item, grandchild_items, animapping, anilist_media in self.map_media(
            item
        ):
            debug_log_title = self._debug_log_title(item=item, animapping=animapping)
            debug_log_ids = self._debug_log_ids(
                key=child_item.ratingKey,
                plex_id=child_item.guid,
                guids=guids,
                anilist_id=anilist_media.id,
            )

            log.debug(
                f"{self.__class__.__name__}: Found AniList entry for {item.type} "
                f"{debug_log_title} {debug_log_ids}"
            )

            try:
                self.sync_media(
                    item=item,
                    child_item=child_item,
                    grandchild_items=grandchild_items,
                    anilist_media=anilist_media,
                    animapping=animapping,
                )
                self.sync_stats.covered |= set(grandchild_items)
            except Exception:
                log.error(
                    f"{self.__class__.__name__}: Failed to process {item.type} "
                    f"{debug_log_title} {debug_log_ids}: ",
                    exc_info=True,
                )
                self.sync_stats.failed += 1

        return self.sync_stats

    @abstractmethod
    def map_media(self, item: T) -> Iterator[tuple[S, list[E], AniMap, Media]]:
        """Maps a Plex item to potential AniList matches.

        Must be implemented by subclasses to handle different
        media types and structures.

        Args:
            item (T): Plex media item to map

        Returns:
            Iterator[tuple[S, list[E], AniMap, Media]]: Mapping matches (child, grandchild, animapping, anilist_media)
        """
        pass

    @abstractmethod
    def search_media(self, item: T, child_item: S) -> Media | None:
        """Searches for matching AniList entry by title.

        Must be implemented by subclasses to handle different
        search strategies for movies vs shows.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync

        Returns:
            Media | None: Matching AniList entry or None if not found
        """
        pass

    def _best_search_result(self, title: str, results: list[Media]) -> Media | None:
        """Finds the best matching AniList entry using fuzzy string matching.

        Args:
            title (str): Title to match against
            results (list[Media]): List of potential Media matches from AniList

        Returns:
            Media | None: Best matching Media entry above threshold, or None if no match meets threshold
        """
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
        self,
        item: T,
        child_item: S,
        grandchild_items: list[E],
        anilist_media: Media,
        animapping: AniMap,
    ) -> None:
        """Synchronizes a matched media item with AniList.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync
            grandchild_items (list[E]): Grandchild items to extract data from
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information
        """
        guids = ParsedGuids.from_guids(item.guids)

        debug_log_title = self._debug_log_title(item=item, animapping=animapping)
        debug_log_ids = self._debug_log_ids(
            key=child_item.ratingKey,
            plex_id=child_item.guid,
            guids=guids,
            anilist_id=anilist_media.id,
        )

        anilist_media_list = anilist_media.media_list_entry
        plex_media_list = self._get_plex_media_list(
            item=item,
            child_item=child_item,
            grandchild_items=grandchild_items,
            anilist_media=anilist_media,
            animapping=animapping,
        )

        if anilist_media_list:
            anilist_media_list.unset_fields(self.excluded_sync_fields)
        plex_media_list.unset_fields(self.excluded_sync_fields)

        final_media_list = self._merge_media_lists(
            anilist_media_list=anilist_media_list, plex_media_list=plex_media_list
        )

        if final_media_list == anilist_media_list:
            log.info(
                f"{self.__class__.__name__}: Skipping {item.type} because it is already up to date "
                f"{debug_log_title} {debug_log_ids}"
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
            self.sync_stats.synced += 1
            self.sync_stats.deleted += 1
            return

        if not final_media_list.status:
            log.info(
                f"{self.__class__.__name__}: Skipping {item.type} due to no activity "
                f"{debug_log_title} {debug_log_ids}"
            )
            self.sync_stats.skipped += 1
            return

        log.info(
            f"{self.__class__.__name__}: Syncing AniList entry for {item.type} "
            f"{debug_log_title} {debug_log_ids}"
        )
        log.info(f"\t\tBEFORE => {anilist_media_list}")
        log.info(f"\t\tAFTER  => {final_media_list}")
        log.info(
            f"\t\tDIFF   => {MediaList.diff(anilist_media_list, final_media_list)}"
        )

        self.anilist_client.update_anime_entry(final_media_list)

        log.info(
            f"{self.__class__.__name__}: Synced {item.type} "
            f"{debug_log_title} {debug_log_ids}"
        )
        self.sync_stats.synced += 1

    def _get_plex_media_list(
        self,
        item: T,
        child_item: S,
        grandchild_items: list[E],
        anilist_media: Media,
        animapping: AniMap,
    ) -> MediaList:
        """Creates a MediaList object from Plex states and AniMap data.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync
            grandchild_items (list[E]): Grandchild items to extract data from
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            MediaList: New MediaList object populated with current Plex states
        """
        kwargs = {
            "item": item,
            "child_item": child_item,
            "grandchild_items": grandchild_items,
            "anilist_media": anilist_media,
            "animapping": animapping,
        }

        media_list = MediaList(
            id=anilist_media.media_list_entry
            and anilist_media.media_list_entry.id
            or 0,
            user_id=self.anilist_client.user.id,
            media_id=anilist_media.id,
            status=self._calculate_status(**kwargs),
            progress=self._calculate_progress(**kwargs),
            repeat=self._calculate_repeats(**kwargs),
        )

        if media_list.status is None:
            return media_list

        notes = None
        if "notes" not in self.excluded_sync_fields:
            notes = self.plex_client.get_user_review(
                child_item
            ) or self.plex_client.get_user_review(item)

        if media_list.status > MediaListStatus.PLANNING:
            media_list.started_at = self._calculate_started_at(**kwargs)
        if media_list.status >= MediaListStatus.COMPLETED:
            media_list.completed_at = self._calculate_completed_at(**kwargs)
            media_list.score = self._calculate_score(**kwargs)
            media_list.notes = notes

        return media_list

    @abstractmethod
    def _calculate_status(
        self,
        item: T,
        child_item: S,
        grandchild_items: list[E],
        anilist_media: Media,
        animapping: AniMap,
    ) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync
            grandchild_items (list[E]): Grandchild items to extract data from
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            MediaListStatus | None: Watch status for the media item
        """
        pass

    @abstractmethod
    def _calculate_score(
        self,
        item: T,
        child_item: S,
        grandchild_items: list[E],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the user rating for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync
            grandchild_items (list[E]): Grandchild items to extract data from
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: User rating for the media item
        """
        pass

    @abstractmethod
    def _calculate_progress(
        self,
        item: T,
        child_item: S,
        grandchild_items: list[E],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the progress for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync
            grandchild_items (list[E]): Grandchild items to extract data from
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: Progress for the media item
        """
        pass

    @abstractmethod
    def _calculate_repeats(
        self,
        item: T,
        child_item: S,
        grandchild_items: list[E],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the number of repeats for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync
            grandchild_items (list[E]): Grandchild items to extract data from
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: Number of repeats for the media item
        """
        pass

    @abstractmethod
    def _calculate_started_at(
        self,
        item: T,
        child_item: S,
        grandchild_items: list[E],
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync
            grandchild_items (list[E]): Grandchild items to extract data from
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            FuzzyDate | None: Start date for the media item
        """
        pass

    @abstractmethod
    def _calculate_completed_at(
        self,
        item: T,
        child_item: S,
        grandchild_items: list[E],
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync
            grandchild_items (list[E]): Grandchild items to extract data from
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            FuzzyDate | None: Completion date for the media item
        """
        pass

    @abstractmethod
    def _debug_log_title(
        self,
        item: T,
        animapping: AniMap | None = None,
    ) -> str:
        """Creates a debug-friendly string of media titles.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item
            animapping (AniMap | None): AniMap entry for the media

        Returns:
            str: Debug-friendly string of media titles
        """
        pass

    @abstractmethod
    def _debug_log_ids(
        self, key: int, plex_id: str, guids: ParsedGuids, anilist_id: int | None = None
    ) -> str:
        """Creates a debug-friendly string of media identifiers.

        Must be implemented by subclasses to handle different media types.

        Args:
            key (int): Plex rating key
            plex_id (str): Plex ID
            guids (ParsedGuids): Plex GUIDs
            anilist_id (int | None): AniList ID

        Returns:
            str: Debug-friendly string of media identifiers
        """
        pass

    def _normalize_score(self, score: int | float | None) -> int | float | None:
        """Normalizes a 0-10 point rating to the user's preferred scale.

        Note:
            Plex uses a scale of 0-5 with half-steps in the UI but the API uses 0-10 points.

        Args:
            score (int | float | None): User rating to normalize
        Returns:
            int | float | None: Normalized rating or None if no rating
        """
        if score is None:
            return None
        score = round(score)

        scale = self.anilist_client.user.media_list_options.score_format

        match scale:
            case ScoreFormat.POINT_100:
                return score * 10
            case ScoreFormat.POINT_10_DECIMAL:
                return score * 1.0
            case ScoreFormat.POINT_10:
                return score * 1
            case ScoreFormat.POINT_5:
                return round(score / 2)
            case ScoreFormat.POINT_3:
                return round(score / 3.33)
            case None:
                return score

    def _merge_media_lists(
        self,
        anilist_media_list: MediaList | None,
        plex_media_list: MediaList,
    ) -> MediaList:
        """Merges Plex and AniList states using defined comparison rules.

        Args:
            anilist_media_list (MediaList | None): Current AniList state
            plex_media_list (MediaList): Current Plex state

        Returns:
            MediaList: New MediaList containing merged state based on comparison rules
        """
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
            """Determines if a field should be updated based on the comparison rule.

            Args:
                op (str): Comparison rule
                p_val: Plex value
                a_val: AniList value

            Returns:
                    bool: True if the field should be updated, False otherwise
            """
            if p_val is None:
                return False
            if a_val is None:
                return True
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
