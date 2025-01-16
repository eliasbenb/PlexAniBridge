from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Iterator, TypeVar

from plexapi.media import Guid
from plexapi.video import Movie, Season, Show
from thefuzz import fuzz

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.models.anilist import FuzzyDate, Media, MediaList, MediaListStatus, ScoreFormat
from src.models.animap import AniMap
from src.settings import SyncField

T = TypeVar("T", bound=Movie | Show)  # Section item
S = TypeVar("S", bound=Movie | Season)  # Item child (season)


@dataclass
class ParsedGuids:
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

        Note:
            - Handles both string (IMDB) and integer (TVDB/TMDB) IDs
            - Silently skips invalid or unknown GUID formats
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

    def __iter__(self) -> Iterator[tuple[str, int | str | None]]:
        """Enables iteration over non-None GUIDs.

        Returns:
            Iterator[tuple[str, int | str | None]]: Iterator of (service, id) pairs
        """
        return iter(self.__dict__.items())

    def __str__(self) -> str:
        """Creates a debug-friendly string representation.

        Returns:
            str: Comma-separated list of non-None IDs
            Example: "tvdb_id: 123456, imdb_id: tt1234567"
        """
        return ", ".join(f"{k}_id: {v}" for k, v in self if v is not None)


@dataclass
class SyncStats:
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
    failed: int = 0

    def __add__(self, other: "SyncStats") -> "SyncStats":
        return SyncStats(
            self.synced + other.synced,
            self.deleted + other.deleted,
            self.skipped + other.skipped,
            self.failed + other.failed,
        )


class BaseSyncClient(ABC, Generic[T, S]):
    """Abstract base class for media synchronization between Plex and AniList.

    Provides core synchronization logic while allowing specialized implementations
    for different media types through abstract methods.

    Type Parameters:
        T: Main media type (Movie or Show)
        S: Subitem type (Movie or Season)

    Attributes:
        anilist_client (AniListClient): Client for AniList API operations
        animap_client (AniMapClient): Client for ID mapping lookups
        plex_client (PlexClient): Client for Plex server operations
        excluded_sync_fields (list[SyncField]): Fields to ignore during sync
        destructive_sync (bool): Whether to allow deletions on AniList
        fuzzy_search_threshold (int): Minimum similarity for title matching
        sync_stats (SyncStats): Current synchronization statistics

    Core Features:
        - Media mapping and lookup
        - Title-based fuzzy matching
        - Status calculation and progress tracking
        - Bidirectional sync with conflict resolution
        - Detailed logging and statistics
    """

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
        """Processes a single media item for synchronization.

        Main workflow:
        1. Parse media identifiers
        2. Map to AniList entries using IDs or title search
        3. Calculate sync states
        4. Update AniList as needed

        Args:
            item (T): Plex media item to process

        Returns:
            SyncStats: Updated synchronization statistics

        Note:
            Handles both direct matches and multi-episode seasons
            through the map_media() abstraction
        """
        guids = ParsedGuids.from_guids(item.guids)
        log.debug(
            f"{self.__class__.__name__}: Processing {item.type} {self._debug_log_title(item)} "
            f"{self._debug_log_ids(item.ratingKey, item.guid, guids)}"
        )

        for subitem, animapping, guids in self.map_media(item=item):
            try:
                anilist_media = None
                if animapping and animapping.anilist_id:
                    anilist_media = self.anilist_client.get_anime(animapping.anilist_id)
                    match_method = "mapping lookup"
                elif subitem.type != "season" or subitem.seasonNumber > 0:
                    anilist_media = self.search_media(item=item, subitem=subitem)
                    match_method = "title search"

                if not anilist_media:
                    log.warning(
                        f"{self.__class__.__name__}: No suitable AniList results found during mapping "
                        f"lookup or title search for {item.type} {self._debug_log_title(item, subitem)} "
                        f"{self._debug_log_ids(subitem.ratingKey, subitem.guid, guids)}"
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
                    f"{self._debug_log_ids(subitem.ratingKey, subitem.guid, guids, anilist_media.id)}"
                )

                self.sync_media(
                    item=item,
                    subitem=subitem,
                    anilist_media=anilist_media,
                    animapping=animapping,
                )
            except Exception as e:
                log.exception(
                    f"{self.__class__.__name__}: Failed to process {item.type} "
                    f"{self._debug_log_title(item, subitem)} "
                    f"{self._debug_log_ids(subitem.ratingKey, subitem.guid, guids)}",
                    exc_info=e,
                )
                self.sync_stats.failed += 1

        return self.sync_stats

    @abstractmethod
    def map_media(self, item: T) -> Iterator[tuple[S, AniMap | None]]:
        """Maps a Plex item to potential AniList matches.

        Must be implemented by subclasses to handle different
        media types and structures.

        Args:
            item (T): Plex media item to map

        Returns:
            Iterator[tuple[S, AniMap | None]]: Potential matches
        """
        pass

    @abstractmethod
    def search_media(self, item: T, subitem: S) -> Media | None:
        """Searches for matching AniList entry by title.

        Must be implemented by subclasses to handle different
        search strategies for movies vs shows.

        Args:
            item (T): Main Plex item
            subitem (S): Specific item to match

        Returns:
            Media | None: Matching AniList entry or None if not found
        """
        pass

    def _best_search_result(self, title: str, results: list[Media]) -> Media | None:
        """Finds the best matching AniList entry using fuzzy string matching.

        Args:
            title (str): Title to match against
            results (list[Media]): Potential matches from AniList

        Returns:
            Media | None: Best match above threshold, or None if no good match

        Note:
            Uses fuzz.ratio from thefuzz library for string similarity
            Compares against all available title variants
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
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> SyncStats:
        """Synchronizes a matched media item with AniList.

        Workflow:
        1. Get current states from both services
        2. Apply excluded fields
        3. Merge states using comparison rules
        4. Update or delete on AniList as needed

        Args:
            item (T): Main Plex media item
            subitem (S): Specific item to sync (same as item for movies)
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Fields Synced (unless excluded):
            - Watch status
            - Score/rating
            - Progress (episodes watched)
            - Rewatch count
            - User notes/review
            - Start/completion dates

        Note:
            - Destructive sync allows deleting entries
            - Skips update if no changes needed
            - Uses _merge_media_lists for conflict resolution
        """
        guids = ParsedGuids.from_guids(item.guids)

        anilist_media_list = anilist_media.media_list_entry or None
        plex_media_list = self._get_plex_media_list(
            item=item,
            subitem=subitem,
            anilist_media=anilist_media,
            animapping=animapping,
        )

        debug_log_title_kwargs = {
            "item": item,
            "subitem": subitem
            if animapping.tvdb_id and animapping.tvdb_season != -1
            else None,
            "extra_title": None
            if animapping.tvdb_season != -1
            else f"(001 - {anilist_media.episodes})",
        }
        debug_log_ids_kwargs = {
            "key": subitem.ratingKey,
            "plex_id": subitem.guid,
            "guids": guids,
            "anilist_id": animapping.anilist_id,
        }

        if anilist_media_list:
            anilist_media_list.unset_fields(self.excluded_sync_fields)
        plex_media_list.unset_fields(self.excluded_sync_fields)

        final_media_list = self._merge_media_lists(
            anilist_media_list=anilist_media_list, plex_media_list=plex_media_list
        )

        if final_media_list == anilist_media_list:
            log.info(
                f"{self.__class__.__name__}: Skipping {item.type} because it is already up to date "
                f"{self._debug_log_title(**debug_log_title_kwargs)} "
                f"{self._debug_log_ids(**debug_log_ids_kwargs)}"
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
                f"{self._debug_log_title(**debug_log_title_kwargs)} "
                f"{self._debug_log_ids(**debug_log_ids_kwargs)}"
            )
            self.sync_stats.skipped += 1
            return

        log.debug(
            f"{self.__class__.__name__}: Syncing AniList entry for {item.type} "
            f"{self._debug_log_title(**debug_log_title_kwargs)} "
            f"{self._debug_log_ids(**debug_log_ids_kwargs)}"
        )
        log.debug(f"\t\tBEFORE => {anilist_media_list}")
        log.debug(f"\t\tAFTER  => {final_media_list}")

        self.anilist_client.update_anime_entry(final_media_list)

        log.info(
            f"{self.__class__.__name__}: Synced {item.type} {self._debug_log_title(**debug_log_title_kwargs)} "
            f"{self._debug_log_ids(**debug_log_ids_kwargs)}"
        )
        self.sync_stats.synced += 1

    def _get_plex_media_list(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> MediaList:
        """Creates a MediaList object from Plex states and AniMap data.

        Args:
            item (T): Main Plex media item
            subitem (S): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            MediaList: MediaList object with updated states
        """
        media_list = MediaList(
            id=anilist_media.media_list_entry
            and anilist_media.media_list_entry.id
            or 0,
            user_id=self.anilist_client.user.id,
            media_id=anilist_media.id,
            status=self._calculate_status(
                item=item,
                subitem=subitem,
                anilist_media=anilist_media,
                animapping=animapping,
            ),
            progress=self._calculate_progress(
                item=item,
                subitem=subitem,
                anilist_media=anilist_media,
                animapping=animapping,
            ),
            repeat=self._calculate_repeats(
                item=item,
                subitem=subitem,
                anilist_media=anilist_media,
                animapping=animapping,
            ),
        )

        if media_list.status is None:
            return media_list

        notes = None
        if "notes" not in self.excluded_sync_fields:
            notes = self.plex_client.get_user_review(
                subitem
            ) or self.plex_client.get_user_review(item)

        if media_list.status > MediaListStatus.PLANNING:
            media_list.started_at = self._calculate_started_at(
                item=item,
                subitem=subitem,
                anilist_media=anilist_media,
                animapping=animapping,
            )
        if media_list.status >= MediaListStatus.COMPLETED:
            media_list.completed_at = self._calculate_completed_at(
                item=item,
                subitem=subitem,
                anilist_media=anilist_media,
                animapping=animapping,
            )
            media_list.score = self._calculate_score(
                item=item,
                subitem=subitem,
                anilist_media=anilist_media,
                animapping=animapping,
            )
            media_list.notes = notes

        return media_list

    @abstractmethod
    def _calculate_status(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Main Plex media item
            subitem (S): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            MediaListStatus | None: Watch status for the media item
        """
        pass

    @abstractmethod
    def _calculate_score(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> int | None:
        """Calculates the user rating for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Main Plex media item
            subitem (S): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: User rating for the media item
        """
        pass

    @abstractmethod
    def _calculate_progress(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> int | None:
        """Calculates the progress for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Main Plex media item
            subitem (S): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: Progress for the media item
        """
        pass

    @abstractmethod
    def _calculate_repeats(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> int | None:
        """Calculates the number of repeats for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Main Plex media item
            subitem (S): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: Number of repeats for the media item
        """
        pass

    @abstractmethod
    def _calculate_started_at(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Main Plex media item
            subitem (S): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            FuzzyDate | None: Start date for the media item
        """
        pass

    @abstractmethod
    def _calculate_completed_at(
        self, item: T, subitem: S, anilist_media: Media, animapping: AniMap
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (T): Main Plex media item
            subitem (S): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            FuzzyDate | None: Completion date for the media item
        """
        pass

    def _normalize_score(self, score: int | None) -> int | float | None:
        """Normalizes a 0-10 point rating to the user's preferred scale.

        Note:
            Plex uses a scale of 0-5 with half-steps in the UI but the API uses 0-10 points.

        Args:
            score (int | float | None): User rating to normalize
        Returns:
            int | None: Normalized rating or None if no rating
        """
        if score is None:
            return None

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

        Rules by field:
            score: Update if different
            notes: Update if different
            progress: Update if Plex value is higher (or destructive)
            repeat: Update if Plex value is higher (or destructive)
            status: Update if Plex status is higher (or destructive)
            started_at: Update if Plex date is earlier (or destructive)
            completed_at: Update if Plex date is earlier (or destructive)

        Args:
            anilist_media_list (MediaList | None): Current AniList state
            plex_media_list (MediaList): Current Plex state

        Returns:
            MediaList: Merged state to apply to AniList

        Note:
            Destructive sync ignores the usual comparison rules and always uses the Plex value
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

    def _debug_log_title(
        self, item: T, subitem: S | None = None, extra_title: str | None = None
    ) -> str:
        """Creates a debug-friendly string of media titles.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args
            item (T): Plex media item
            subitem (S | None): Specific item to sync. Defaults to None
            extra_title (str | None): An additional string to append to the title. Defaults to None

        Returns:
            str: Debug-friendly string of media titles
        """
        extra_title = f" | {extra_title}" if extra_title else ""
        if subitem and item != subitem:
            return f"$$'{item.title} | {subitem.title}{extra_title}'$$"
        return f"$$'{item.title}{extra_title}'$$"

    def _debug_log_ids(
        self,
        key: int,
        plex_id: str,
        guids: ParsedGuids,
        anilist_id: int | None = None,
    ) -> str:
        """Creates a debug-friendly string of media identifiers.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            key (int): Plex rating key
            plex_id (str): Plex ID
            guids (ParsedGuids): Plex GUIDs
            anilist_id (int | None): AniList ID

        Returns:
            str: Debug-friendly string of media identifiers
        """
        return f"$${{key: {key}, plex_id: {plex_id}, {guids}{f', anilist_id: {anilist_id}' if anilist_id else ''}}}$$"
