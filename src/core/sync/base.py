"""Abstract base class for media synchronization between Plex and AniList."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Generic, TypeVar

from rapidfuzz import fuzz

from plexapi.video import Episode, Movie, Season, Show
from src import log
from src.config.settings import SyncField
from src.core import AniListClient, AniMapClient, PlexClient
from src.models.anilist import FuzzyDate, Media, MediaList, MediaListStatus, ScoreFormat
from src.models.animap import AniMap
from src.models.sync import (
    ItemIdentifier,
    ParsedGuids,
    SyncOutcome,
    SyncStats,
)
from src.utils.types import Comparable

T = TypeVar("T", bound=Movie | Show)  # Section item
S = TypeVar("S", bound=Movie | Season)  # Item child (season)
E = TypeVar("E", bound=list[Movie] | list[Episode])  # Item grandchild (episode)


class BaseSyncClient(ABC, Generic[T, S, E]):
    """Abstract base class for media synchronization between Plex and AniList.

    Provides core synchronization logic while allowing specialized implementations
    for different media types through abstract methods.

    Type Parameters:
        T: Main media type (Movie or Show).
        S: Child item type (Movie or Season).
        E: Grandchild item type (list[Movie] or list[Episode]).
    """

    def __init__(
        self,
        anilist_client: AniListClient,
        animap_client: AniMapClient,
        plex_client: PlexClient,
        excluded_sync_fields: list[SyncField],
        full_scan: bool,
        destructive_sync: bool,
        search_fallback_threshold: int,
        batch_requests: bool,
        profile_name: str,
    ) -> None:
        """Initializes a new synchronization client.

        Args:
            anilist_client (AniListClient): AniList API client.
            animap_client (AniMapClient): AniMap API client.
            plex_client (PlexClient): Plex API client.
            excluded_sync_fields (list[SyncField]): Fields to exclude from
                                                    synchronization.
            full_scan (bool): Whether to perform a full scan of all media.
            destructive_sync (bool): Whether to delete AniList entries not in Plex.
            search_fallback_threshold (int): Minimum similarity ratio (0-100) for fuzzy
                                             title matching.
            batch_requests (bool): Whether to use batch requests to reduce API calls.
            profile_name (str): Name of the sync profile for logging.
        """
        self.anilist_client = anilist_client
        self.animap_client = animap_client
        self.plex_client = plex_client

        self.excluded_sync_fields = [field.value for field in excluded_sync_fields]
        self.full_scan = full_scan
        self.destructive_sync = destructive_sync
        self.search_fallback_threshold = search_fallback_threshold
        self.batch_requests = batch_requests

        self.profile_name = profile_name

        self.sync_stats = SyncStats()

        extra_fields: dict[SyncField, Callable] = {
            SyncField.STATUS: lambda **kwargs: self._calculate_status(**kwargs),
            SyncField.PROGRESS: lambda **kwargs: self._calculate_progress(**kwargs),
            SyncField.REPEAT: lambda **kwargs: self._calculate_repeats(**kwargs),
            SyncField.SCORE: lambda **kwargs: self._calculate_score(**kwargs),
            SyncField.NOTES: lambda **kwargs: self._calculate_notes(**kwargs),
            SyncField.STARTED_AT: lambda **kwargs: self._calculate_started_at(**kwargs),
            SyncField.COMPLETED_AT: lambda **kwargs: self._calculate_completed_at(
                **kwargs
            ),
        }
        self._extra_fields = {
            k: v for k, v in extra_fields.items() if k not in self.excluded_sync_fields
        }

        self.queued_batch_requests: list[MediaList] = []

    def clear_cache(self) -> None:
        """Clears the cache for all decorated methods in the class.

        Iterates through all class attributes and calls `cache_clear()`
        on any cached methods to free memory and ensure fresh data.
        """
        for attr in dir(self):
            if callable(getattr(self, attr)) and hasattr(
                getattr(self, attr), "cache_clear"
            ):
                getattr(self, attr).cache_clear()

    async def process_media(self, item: T) -> None:
        """Processes a single media item for synchronization.

        Args:
            item (T): Grandparent Plex media item to sync.
        """
        guids = ParsedGuids.from_guids(item.guids)

        debug_log_title = self._debug_log_title(item=item)
        debug_log_ids = self._debug_log_ids(
            key=item.ratingKey,
            plex_id=item.guid,
            guids=guids,
        )

        log.debug(
            f"{self.__class__.__name__}: [{self.profile_name}] Processing {item.type} "
            f"{debug_log_title} {debug_log_ids}"
        )

        item_id = ItemIdentifier.from_item(item)

        all_trackable_items = await self._get_all_trackable_items(item)
        if all_trackable_items:
            self.sync_stats.register_pending_items(all_trackable_items)
        self.sync_stats.track_item(item_id, SyncOutcome.PENDING)

        async for (
            child_item,
            grandchild_items,
            animapping,
            anilist_media,
        ) in self.map_media(item):
            grandchild_ids = ItemIdentifier.from_items(grandchild_items)

            debug_log_title = self._debug_log_title(item=item, animapping=animapping)
            debug_log_ids = self._debug_log_ids(
                key=child_item.ratingKey,
                plex_id=child_item.guid,
                guids=guids,
                anilist_id=anilist_media.id,
            )

            log.debug(
                f"{self.__class__.__name__}: [{self.profile_name}] Found AniList entry "
                f"for {item.type} {debug_log_title} {debug_log_ids}"
            )

            try:
                outcome = await self.sync_media(
                    item=item,
                    child_item=child_item,
                    grandchild_items=grandchild_items,
                    anilist_media=anilist_media,
                    animapping=animapping,
                )
                self.sync_stats.track_items(grandchild_ids, outcome)
                self.sync_stats.track_item(item_id, outcome)

            except Exception:
                log.error(
                    f"{self.__class__.__name__}: [{self.profile_name}] Failed to "
                    f"process {item.type} {debug_log_title} {debug_log_ids}",
                    exc_info=True,
                )
                self.sync_stats.track_items(grandchild_ids, SyncOutcome.FAILED)
                self.sync_stats.track_item(item_id, SyncOutcome.FAILED)

    @abstractmethod
    async def _get_all_trackable_items(self, item: T) -> list[ItemIdentifier]:
        """Get all trackable items (episodes/movies) for a given parent item.

        This method should return all episodes or movies that should be tracked
        for synchronization purposes, even if they might not ultimately be processed.

        Args:
            item (T): Grandparent Plex media item.

        Returns:
            list[ItemIdentifier]: List of all trackable items for this parent.
        """
        pass

    @abstractmethod
    def map_media(self, item: T) -> AsyncIterator[tuple[S, E, AniMap, Media]]:
        """Maps a Plex item to potential AniList matches.

        Must be implemented by subclasses to handle different media types and
        structures.

        Args:
            item (T): Plex media item to map.

        Yields:
            tuple[S, E, AniMap, Media]: Mapping matches as tuples containing:
                - child (S): Child item (Movie or Season).
                - grandchild (E): Grandchild items (list of Movies or Episodes).
                - animapping (AniMap): AniMap entry with ID mappings.
                - anilist_media (Media): Matched AniList media entry.
        """
        pass

    @abstractmethod
    async def search_media(self, item: T, child_item: S) -> Media | None:
        """Searches for matching AniList entry by title.

        Must be implemented by subclasses to handle different
        search strategies for movies vs shows.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.

        Returns:
            Media | None: Matching AniList entry or None if not found.
        """
        pass

    def _best_search_result(self, title: str, results: list[Media]) -> Media | None:
        """Finds the best matching AniList entry using fuzzy string matching.

        Args:
            title (str): Title to match against.
            results (list[Media]): List of potential Media matches from AniList.

        Returns:
            Media | None: Best matching Media entry above threshold, or None if no
                          match meets threshold.
        """
        best_result, best_ratio = None, 0
        for r in results:
            if r.title:
                for t in r.title.titles():
                    current_ratio = fuzz.ratio(title, t)
                    if current_ratio > best_ratio:
                        best_ratio = current_ratio
                        best_result = r
        if best_ratio < self.search_fallback_threshold:
            return None
        return best_result

    async def sync_media(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> SyncOutcome:
        """Synchronizes a matched media item with AniList.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            SyncOutcome: The result of the synchronization operation.
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
        plex_media_list = await self._get_plex_media_list(
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
                f"{self.__class__.__name__}: [{self.profile_name}] Skipping "
                f"{item.type} because it is already up to date "
                f"{debug_log_title} {debug_log_ids}"
            )
            return SyncOutcome.SKIPPED

        if self.destructive_sync and anilist_media_list and not plex_media_list.status:
            log.success(
                f"{self.__class__.__name__}: [{self.profile_name}] Deleting AniList "
                f"entry for {item.type} {debug_log_title} {debug_log_ids}"
            )
            log.success(f"\t\tDELETE: {anilist_media_list}")

            if anilist_media.media_list_entry:
                await self.anilist_client.delete_anime_entry(
                    anilist_media.media_list_entry.id,
                    anilist_media.media_list_entry.media_id,
                )
                return SyncOutcome.DELETED
            return SyncOutcome.SKIPPED

        if not final_media_list.status:
            log.info(
                f"{self.__class__.__name__}: [{self.profile_name}] Skipping "
                f"{item.type} due to no activity {debug_log_title} {debug_log_ids}"
            )
            return SyncOutcome.SKIPPED

        if self.batch_requests:
            log.info(
                f"{self.__class__.__name__}: [{self.profile_name}] Queuing {item.type} "
                f"for batch sync {debug_log_title} {debug_log_ids}"
            )
            log.success(
                f"\t\tQUEUED UPDATE: {
                    MediaList.diff(anilist_media_list, final_media_list)
                }"
            )
            self.queued_batch_requests.append(final_media_list)
            return SyncOutcome.SYNCED  # Will be synced in batch
        else:
            log.info(
                f"{self.__class__.__name__}: [{self.profile_name}] Syncing AniList "
                f"entry for {item.type} {debug_log_title} {debug_log_ids}"
            )
            log.success(
                f"\t\tUPDATE: {MediaList.diff(anilist_media_list, final_media_list)}"
            )
            await self.anilist_client.update_anime_entry(final_media_list)

            log.success(
                f"{self.__class__.__name__}: [{self.profile_name}] Synced {item.type} "
                f"{debug_log_title} {debug_log_ids}"
            )
            return SyncOutcome.SYNCED

    async def batch_sync(self) -> None:
        """Executes batch synchronization of queued media lists.

        Sends all queued media lists to AniList in a single batch request.
        This is more efficient than sending individual requests for each media list.
        """
        if not self.queued_batch_requests:
            return

        log.info(
            f"{self.__class__.__name__}: [{self.profile_name}] Syncing "
            f"{len(self.queued_batch_requests)} items to AniList "
            f"with batch mode "
            f"$${{anilist_id: {[m.media_id for m in self.queued_batch_requests]}}}$$"
        )
        try:
            await self.anilist_client.batch_update_anime_entries(
                self.queued_batch_requests
            )
            log.success(
                f"{self.__class__.__name__}: [{self.profile_name}] Synced "
                f"{len(self.queued_batch_requests)} items to AniList "
                f"with batch mode $${{anilist_id: "
                f"{[m.media_id for m in self.queued_batch_requests]}}}$$"
            )
        finally:
            self.queued_batch_requests.clear()

    async def _get_plex_media_list(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> MediaList:
        """Creates a MediaList object from Plex states and AniMap data.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            MediaList: New MediaList object populated with current Plex states.
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
            status=await self._calculate_status(**kwargs),
        )

        if media_list.status is None:
            return media_list

        for field in self._extra_fields:
            match field:
                case SyncField.STATUS:
                    pass
                case SyncField.REPEAT | SyncField.SCORE | SyncField.COMPLETED_AT:
                    if media_list.status >= MediaListStatus.COMPLETED:
                        setattr(
                            media_list, field, await self._extra_fields[field](**kwargs)
                        )
                case SyncField.STARTED_AT:
                    media_list.started_at = (
                        await self._extra_fields[field](**kwargs)
                        if media_list.status > MediaListStatus.PLANNING
                        else None
                    )
                case _:
                    setattr(
                        media_list, field, await self._extra_fields[field](**kwargs)
                    )

        return media_list

    @abstractmethod
    async def _calculate_status(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            MediaListStatus | None: Watch status for the media item.
        """
        pass

    @abstractmethod
    async def _calculate_score(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | float | None:
        """Calculates the user rating for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            int | float | None: User rating for the media item.
        """
        pass

    @abstractmethod
    async def _calculate_progress(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the progress for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            int | None: Progress for the media item.
        """
        pass

    @abstractmethod
    async def _calculate_repeats(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the number of repeats for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            int | None: Number of repeats for the media item.
        """
        pass

    @abstractmethod
    async def _calculate_started_at(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            FuzzyDate | None: Start date for the media item.
        """
        pass

    @abstractmethod
    async def _calculate_completed_at(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            FuzzyDate | None: Completion date for the media item.
        """
        pass

    @abstractmethod
    async def _calculate_notes(
        self,
        item: T,
        child_item: S,
        grandchild_items: E,
        anilist_media: Media,
        animapping: AniMap,
    ) -> str | None:
        """Chooses the most relevant user notes for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): ID mapping information.

        Returns:
            str | None: User notes for the media item.
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
            item (T): Grandparent Plex media item.
            animapping (AniMap | None): AniMap entry for the media.

        Returns:
            str: Debug-friendly string of media titles.
        """
        pass

    @abstractmethod
    def _debug_log_ids(
        self,
        key: int | str,
        plex_id: str | None,
        guids: ParsedGuids,
        anilist_id: int | None = None,
    ) -> str:
        """Creates a debug-friendly string of media identifiers.

        Must be implemented by subclasses to handle different media types.

        Args:
            key (int): Plex rating key.
            plex_id (str): Plex ID.
            guids (ParsedGuids): Plex GUIDs.
            anilist_id (int | None): AniList ID.

        Returns:
            str: Debug-friendly string of media identifiers.
        """
        pass

    def _normalize_score(self, score: int | float | None) -> int | float | None:
        """Normalizes a 0-10 point rating to the user's preferred scale.

        Plex uses a scale of 0-5 with half-steps in the UI but the API uses 0-10 points.

        Args:
            score (int | float | None): User rating to normalize
        Returns:
            int | float | None: Normalized rating or None if no rating
        """
        if score is None:
            return None
        score = round(score)

        scale = (
            self.anilist_client.user.media_list_options.score_format
            if self.anilist_client.user.media_list_options
            else None
        )

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
            anilist_media_list (MediaList | None): Current AniList state.
            plex_media_list (MediaList): Current Plex state.

        Returns:
            MediaList: New MediaList containing merged state based on comparison rules.
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

        for key, rule in COMPARISON_RULES.items():
            plex_val = getattr(plex_media_list, key)
            anilist_val = getattr(anilist_media_list, key)

            if (
                self.destructive_sync
                and plex_val is not None
                or self._should_update_field(rule, plex_val, anilist_val)
            ):
                setattr(res_media_list, key, plex_val)

        return res_media_list

    def _should_update_field(
        self, op: str, plex_val: Comparable | None, anilist_val: Comparable | None
    ) -> bool:
        """Determines if a field should be updated based on the comparison rule.

        Args:
            op (str): Comparison rule.
            plex_val (Comparable | None): Plex value to compare against.
            anilist_val (Comparable | None): AniList value to compare against.

        Returns:
            bool: True if the field should be updated, False otherwise.
        """
        if anilist_val == plex_val:
            return False
        if anilist_val is None:
            return True
        if plex_val is None:
            return False

        match op:
            case "ne":
                return plex_val != anilist_val
            case "gt":
                return plex_val > anilist_val
            case "gte":
                return plex_val >= anilist_val
            case "lt":
                return plex_val < anilist_val
            case "lte":
                return plex_val <= anilist_val
        return False
