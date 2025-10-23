"""Abstract base class for media synchronization between Plex and AniList."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

from plexapi.media import Guid
from plexapi.video import Episode, Movie, Season, Show
from pydantic import BaseModel
from rapidfuzz import fuzz
from sqlalchemy import or_

from src import log
from src.config.database import db
from src.config.settings import SyncField
from src.core import AniListClient, AniMapClient, PlexClient
from src.core.sync.stats import (
    ItemIdentifier,
    SyncOutcome,
    SyncStats,
)
from src.models.db.animap import AniMap
from src.models.db.pin import Pin
from src.models.db.sync_history import MediaType, SyncHistory
from src.models.schemas.anilist import (
    FuzzyDate,
    Media,
    MediaList,
    MediaListStatus,
    ScoreFormat,
)
from src.utils.types import Comparable

_LEGACY_GUID_MAPPING = {
    "com.plexapp.agents.imdb": "imdb",
    "com.plexapp.agents.tmdb": "tmdb",
    "com.plexapp.agents.themoviedb": "tmdb",
    "com.plexapp.agents.thetvdb": "tvdb",
}


class ParsedGuids(BaseModel):
    """Container for parsed media identifiers from different services.

    Handles parsing and storage of media IDs from various services (TVDB, TMDB, IMDB)
    from Plex's GUID format into a structured format. Provides iteration and string
    representation for debugging.

    Note:
        GUID formats expected from Plex:
        - TVDB: "tvdb://123456" OR "com.plexapp.agents.thetvdb://123456"
        - TMDB: "tmdb://123456" OR "com.plexapp.agents.tmdb://123456" OR "com.plexapp.agents.themoviedb://123456"
        - IMDB: "imdb://tt1234567" OR "com.plexapp.agents.imdb://tt1234567"
    """

    tvdb: int | None = None
    tmdb: int | None = None
    imdb: str | None = None

    @staticmethod
    def from_guids(guids: list[Guid]) -> ParsedGuids:
        """Creates a ParsedGuids instance from a list of Plex GUIDs.

        Args:
            guids (list[Guid]): List of Plex GUID objects

        Returns:
            ParsedGuids: New instance with parsed IDs
        """
        parsed_guids = ParsedGuids()

        for guid in guids:
            if not guid.id:
                continue

            split_guid = guid.id.split("://")
            if len(split_guid) != 2:
                continue

            service = split_guid[0]
            id_part = split_guid[1]

            # Remove query parameters if present (e.g., ?lang=en)
            if "?" in id_part:
                id_part = id_part.split("?")[0]

            attr = _LEGACY_GUID_MAPPING.get(service, service)
            if not hasattr(parsed_guids, attr):
                continue

            try:
                setattr(parsed_guids, attr, int(id_part))
            except ValueError:
                setattr(parsed_guids, attr, str(id_part))

        return parsed_guids

    def __str__(self) -> str:
        """Creates a string representation of the parsed IDs.

        Returns:
            str: String representation of the parsed IDs in a format like
                 "id: xxx, id: xxx, id: xxx"
        """
        return ", ".join(
            f"{field}: {getattr(self, field)}"
            for field in self.__class__.model_fields
            if getattr(self, field) is not None
        )


class BaseSyncClient[
    T: Movie | Show,  # Main media type
    S: Movie | Season,  # Child item type
    E: list[Movie] | list[Episode],  # Grandchild item type
](ABC):
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
        self._pin_cache: dict[int, list[str]] = {}

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
            k: v
            for k, v in extra_fields.items()
            if k.value not in self.excluded_sync_fields
        }

        self.queued_batch_requests: list[MediaList] = []
        # Track batch items for history recording
        self.batch_history_items: list[tuple[T, S, MediaList | None, MediaList]] = []

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
        self._pin_cache.clear()

    def _get_pinned_fields(self, anilist_id: int | None) -> list[str]:
        """Retrieve pinned fields for the current profile and AniList entry."""
        if not anilist_id:
            return []

        cached = self._pin_cache.get(anilist_id)
        if cached is not None:
            return cached

        with db() as ctx:
            pin: Pin | None = (
                ctx.session.query(Pin)
                .filter(
                    Pin.profile_name == self.profile_name,
                    Pin.anilist_id == anilist_id,
                )
                .first()
            )

        fields = list(pin.fields) if pin and pin.fields else []
        self._pin_cache[anilist_id] = fields
        return fields

    async def _create_sync_history(
        self,
        item: T,
        child_item: S | None,
        grandchild_items: E | None,
        media_list_pair: tuple[MediaList | None, MediaList | None],
        animapping: AniMap | None,
        outcome: SyncOutcome,
        error_message: str | None = None,
    ) -> None:
        """Creates a sync history record for tracking synchronization operations.

        Args:
            item (T): Grandparent Plex media item.
            child_item (S): Target child item to sync.
            grandchild_items (E): Grandchild items to extract data from.
            media_list_pair (tuple[MediaList | None, MediaList | None]): Tuple of
                matched AniList media list entries (before and after sync).
            animapping (AniMap | None): ID mapping information.
            outcome (SyncOutcome): Result of the synchronization operation.
            error_message (str | None): Error message if the sync failed.
        """
        _before_state, _after_state = media_list_pair
        before_state = (
            _before_state.model_dump(mode="json") if _before_state is not None else None
        )
        after_state = (
            _after_state.model_dump(mode="json") if _after_state is not None else None
        )

        plex_rating_key = str(item.ratingKey)
        plex_child_rating_key = str(child_item.ratingKey) if child_item else None
        plex_type = MediaType.from_item(item)

        with db() as ctx:
            if outcome == SyncOutcome.SYNCED:
                delete_query = ctx.session.query(SyncHistory).filter(
                    SyncHistory.profile_name == self.profile_name,
                    SyncHistory.plex_rating_key == plex_rating_key,
                    SyncHistory.plex_type == plex_type,
                    SyncHistory.outcome.in_(
                        [SyncOutcome.NOT_FOUND, SyncOutcome.FAILED]
                    ),
                )

                if plex_child_rating_key is not None:
                    delete_query = delete_query.filter(
                        or_(
                            SyncHistory.plex_child_rating_key == plex_child_rating_key,
                            SyncHistory.plex_child_rating_key.is_(None),
                        )
                    )
                else:
                    delete_query = delete_query.filter(
                        SyncHistory.plex_child_rating_key.is_(None)
                    )

                delete_query.delete(synchronize_session=False)

            if outcome == SyncOutcome.SKIPPED:
                # If skipped, no need to create a history record
                return
            if outcome in (SyncOutcome.NOT_FOUND, SyncOutcome.FAILED):
                # On error, upsert existing record if it exists
                existing_record = (
                    ctx.session.query(SyncHistory)
                    .filter(
                        SyncHistory.profile_name == self.profile_name,
                        SyncHistory.plex_rating_key == plex_rating_key,
                        SyncHistory.plex_child_rating_key == plex_child_rating_key,
                        SyncHistory.plex_type == plex_type,
                        SyncHistory.outcome == outcome,
                    )
                    .first()
                )
                if existing_record:
                    if existing_record.error_message == error_message:
                        return
                    existing_record.before_state = before_state
                    existing_record.after_state = after_state
                    existing_record.error_message = error_message
                    existing_record.timestamp = datetime.now(UTC)
                    ctx.session.commit()
                    return

            try:
                history_record = SyncHistory(
                    profile_name=self.profile_name,
                    plex_guid=item.guid,
                    plex_rating_key=plex_rating_key,
                    plex_child_rating_key=plex_child_rating_key,
                    plex_type=plex_type,
                    anilist_id=animapping.anilist_id if animapping else None,
                    outcome=outcome,
                    before_state=before_state,
                    after_state=after_state,
                    error_message=error_message,
                )

                ctx.session.add(history_record)
                ctx.session.commit()

            except Exception as e:
                log.error(
                    f"Failed to create sync history record for {item.title} "
                    f"({item.ratingKey}): {e}",
                    exc_info=True,
                )
                ctx.session.rollback()

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
        else:
            log.debug(
                f"{self.__class__.__name__}: [{self.profile_name}] "
                f"Skipping {item.type} because it has no eligible child items "
                f"{debug_log_title} {debug_log_ids}"
            )
            self.sync_stats.track_item(item_id, SyncOutcome.SKIPPED)
            return

        found_match = False
        async for (
            child_item,
            grandchild_items,
            animapping,
            anilist_media,
        ) in self.map_media(item):
            found_match = True
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

            except Exception as e:
                log.error(
                    f"{self.__class__.__name__}: [{self.profile_name}] Failed to "
                    f"process {item.type} {debug_log_title} {debug_log_ids}",
                    exc_info=True,
                )

                await self._create_sync_history(
                    item=item,
                    child_item=child_item,
                    grandchild_items=grandchild_items,
                    media_list_pair=(None, None),
                    animapping=animapping,
                    outcome=SyncOutcome.FAILED,
                    error_message=str(e),
                )

                self.sync_stats.track_items(grandchild_ids, SyncOutcome.FAILED)
                self.sync_stats.track_item(item_id, SyncOutcome.FAILED)

        if not found_match:
            await self._create_sync_history(
                item=item,
                child_item=None,
                grandchild_items=None,
                media_list_pair=(None, None),
                animapping=None,
                outcome=SyncOutcome.NOT_FOUND,
                error_message=None,
            )
            self.sync_stats.track_item(item_id, SyncOutcome.NOT_FOUND)

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

        original_anilist_media_list = (
            anilist_media.media_list_entry.model_copy(deep=True)
            if anilist_media.media_list_entry
            else None
        )
        working_anilist_media_list = (
            original_anilist_media_list.model_copy(deep=True)
            if original_anilist_media_list
            else None
        )

        plex_media_list = await self._get_plex_media_list(
            item=item,
            child_item=child_item,
            grandchild_items=grandchild_items,
            anilist_media=anilist_media,
            animapping=animapping,
        )

        base_plex_media_list = plex_media_list.model_copy(deep=True)

        plex_media_list.unset_fields(self.excluded_sync_fields)

        final_media_list = self._merge_media_lists(
            anilist_media_list=working_anilist_media_list,
            plex_media_list=plex_media_list,
            excluded_fields=set(self.excluded_sync_fields),
        )

        if (
            working_anilist_media_list
            and final_media_list == working_anilist_media_list
        ):
            log.info(
                f"{self.__class__.__name__}: [{self.profile_name}] Skipping "
                f"{item.type} because it is already up to date "
                f"{debug_log_title} {debug_log_ids}"
            )
            return SyncOutcome.SKIPPED

        pinned_fields: list[str] = self._get_pinned_fields(anilist_media.id)

        if pinned_fields:
            effective_excluded_fields = list(
                {*self.excluded_sync_fields, *pinned_fields}
            )

            working_anilist_media_list = (
                original_anilist_media_list.model_copy(deep=True)
                if original_anilist_media_list
                else None
            )
            plex_media_list = base_plex_media_list.model_copy(deep=True)

            plex_media_list.unset_fields(effective_excluded_fields)

            final_media_list = self._merge_media_lists(
                anilist_media_list=working_anilist_media_list,
                plex_media_list=plex_media_list,
                excluded_fields=set(effective_excluded_fields),
            )

            if original_anilist_media_list:
                for field in pinned_fields:
                    if hasattr(final_media_list, field):
                        setattr(
                            final_media_list,
                            field,
                            getattr(original_anilist_media_list, field),
                        )
                    if working_anilist_media_list and hasattr(
                        working_anilist_media_list, field
                    ):
                        setattr(
                            working_anilist_media_list,
                            field,
                            getattr(original_anilist_media_list, field),
                        )

            if (
                working_anilist_media_list
                and final_media_list == working_anilist_media_list
            ):
                log.info(
                    f"{self.__class__.__name__}: [{self.profile_name}] Skipping "
                    f"{item.type} because it is already up to date "
                    f"{debug_log_title} {debug_log_ids}"
                )
                return SyncOutcome.SKIPPED

        if (
            self.destructive_sync
            and original_anilist_media_list
            and not plex_media_list.status
        ):
            log.success(
                f"{self.__class__.__name__}: [{self.profile_name}] Deleting AniList "
                f"entry for {item.type} {debug_log_title} {debug_log_ids}"
            )
            log.success(f"\t\tDELETE: {original_anilist_media_list}")

            if anilist_media.media_list_entry:
                await self.anilist_client.delete_anime_entry(
                    anilist_media.media_list_entry.id,
                    anilist_media.media_list_entry.media_id,
                )

                await self._create_sync_history(
                    item=item,
                    child_item=child_item,
                    grandchild_items=grandchild_items,
                    media_list_pair=(original_anilist_media_list, None),
                    animapping=animapping,
                    outcome=SyncOutcome.DELETED,
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
                    MediaList.diff(original_anilist_media_list, final_media_list)
                }"
            )
            self.queued_batch_requests.append(final_media_list)

            # Store for batch history tracking
            self.batch_history_items.append(
                (item, child_item, original_anilist_media_list, final_media_list)
            )

            return SyncOutcome.SYNCED  # Will be synced in batch
        else:
            log.info(
                f"{self.__class__.__name__}: [{self.profile_name}] Syncing AniList "
                f"entry for {item.type} {debug_log_title} {debug_log_ids}"
            )
            log.success(
                "\t\tUPDATE: "
                f"{MediaList.diff(original_anilist_media_list, final_media_list)}"
            )

            try:
                await self.anilist_client.update_anime_entry(final_media_list)

                log.success(
                    f"{self.__class__.__name__}: [{self.profile_name}] Synced "
                    f"{item.type} {debug_log_title} {debug_log_ids}"
                )

                await self._create_sync_history(
                    item=item,
                    child_item=child_item,
                    grandchild_items=grandchild_items,
                    media_list_pair=(original_anilist_media_list, final_media_list),
                    animapping=animapping,
                    outcome=SyncOutcome.SYNCED,
                )

                return SyncOutcome.SYNCED

            except Exception as e:
                log.error(
                    f"Failed to sync {item.type} {debug_log_title} {debug_log_ids}",
                    exc_info=True,
                )

                await self._create_sync_history(
                    item=item,
                    child_item=child_item,
                    grandchild_items=grandchild_items,
                    media_list_pair=(original_anilist_media_list, final_media_list),
                    animapping=animapping,
                    outcome=SyncOutcome.FAILED,
                    error_message=str(e),
                )

                raise

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

            for item, child_item, before_state, after_state in self.batch_history_items:
                await self._create_sync_history(
                    item=item,
                    child_item=child_item,
                    grandchild_items=None,
                    media_list_pair=(before_state, after_state),
                    animapping=None,
                    outcome=SyncOutcome.SYNCED,
                )

        except Exception as e:
            error_msg = str(e)
            log.error(f"Batch sync failed: {e}", exc_info=True)

            for item, child_item, before_state, after_state in self.batch_history_items:
                await self._create_sync_history(
                    item=item,
                    child_item=child_item,
                    grandchild_items=None,
                    media_list_pair=(before_state, after_state),
                    animapping=None,
                    outcome=SyncOutcome.FAILED,
                    error_message=error_msg,
                )

            raise

        finally:
            self.queued_batch_requests.clear()
            self.batch_history_items.clear()

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
            id=(anilist_media.media_list_entry and anilist_media.media_list_entry.id)
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
        excluded_fields: set[str],
    ) -> MediaList:
        """Merges Plex and AniList states using defined comparison rules.

        Args:
            anilist_media_list (MediaList | None): Current AniList state.
            plex_media_list (MediaList): Current Plex state.
            excluded_fields (set[str]): Fields excluded from synchronization.

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

            if self._should_update_field(
                op=rule,
                field_name=key,
                excluded_fields=excluded_fields,
                plex_val=plex_val,
                anilist_val=anilist_val,
            ):
                setattr(res_media_list, key, plex_val)

        return res_media_list

    def _should_update_field(
        self,
        op: str,
        field_name: str,
        excluded_fields: set[str],
        plex_val: Comparable | None,
        anilist_val: Comparable | None,
    ) -> bool:
        """Determines if a field should be updated based on the comparison rule.

        Args:
            op (str): Comparison rule.
            field_name (str): Field being evaluated.
            excluded_fields (set[str]): Fields excluded from synchronization.
            plex_val (Comparable | None): Plex value to compare against.
            anilist_val (Comparable | None): AniList value to compare against.

        Returns:
            bool: True if the field should be updated, False otherwise.
        """
        if field_name in excluded_fields:
            return False
        if self.destructive_sync and plex_val is not None:
            return True
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
