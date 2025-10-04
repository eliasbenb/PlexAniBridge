"""Sync client for Plex shows to AniList."""

import contextlib
import sys
from collections import Counter
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal

from plexapi.video import Episode, EpisodeHistory, MovieHistory, Season, Show
from tzlocal import get_localzone

from src import log
from src.core.sync.base import BaseSyncClient, ParsedGuids
from src.core.sync.stats import ItemIdentifier, SyncOutcome
from src.models.db.animap import AniMap, EpisodeMapping
from src.models.schemas.anilist import FuzzyDate, Media, MediaListStatus
from src.utils.cache import gattl_cache, glru_cache


class ShowSyncClient(BaseSyncClient[Show, Season, list[Episode]]):
    """Sync client for Plex shows to AniList.

    This client handles:
        - Mapping Plex shows to AniList entries using GUIDs (TVDB, TMDB, etc.).
        - Searching for AniList entries by title if no GUID mapping is found.
        - Determining watch status, ratings, progress, repeats, start/completion dates.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the ShowSyncClient with a show ordering cache."""
        super().__init__(*args, **kwargs)
        self._show_ordering_cache: dict[str, Literal["tmdb", "tvdb", ""]] = {}

    async def map_media(
        self, item: Show
    ) -> AsyncIterator[tuple[Season, list[Episode], AniMap, Media]]:
        """Map a Plex show to potential AniList matches.

        Searches for AniList entries that match the provided Plex show using
        TVDB mappings that can span multiple seasons and episodes. Falls back
        to title-based search for unmapped seasons. Only processes seasons
        with watched content unless full_scan is enabled.

        Args:
            item (Show): Plex show to map.

        Yields:
            tuple[Season, list[Episode], AniMap, Media]: Mapping matches with:
                - Season: Primary season for this mapping
                - list[Episode]: List of episodes from mapped season(s)
                - AniMap: AniMap entry with TVDB season mappings
                - Media: Matched AniList media entry
        """
        guids = ParsedGuids.from_guids(item.guids)

        seasons = self.__get_wanted_seasons(item)
        if not seasons:
            return

        # Pre-fetch all episodes of the show. Instead of fetching episodes for each
        # season individually, we can fetch all episodes at once and filter them later.
        episodes_by_season: dict[int, list[Episode]] = {idx: [] for idx in seasons}
        _wanted_episodes = self.__get_wanted_episodes(item)
        for episode in _wanted_episodes:
            if episode.parentIndex in episodes_by_season:
                episodes_by_season[episode.parentIndex].append(episode)

        processed_seasons: set[int] = set()

        effective_show_ordering = self._get_effective_show_ordering(item, guids)
        if not effective_show_ordering:
            log.warning(
                f"Could not determine effective show ordering for "
                f"{self._debug_log_title(item)} "
                f"{self._debug_log_ids(item.ratingKey, item.guid, guids)}"
            )

        animappings = list(
            self.animap_client.get_mappings(
                tmdb=guids.tmdb, tvdb=guids.tvdb, is_movie=False
            )
        )

        for animapping in animappings:
            if not animapping.anilist_id:
                continue

            # Filter the seasons that are relevant to the current mapping
            parsed_mappings = self._get_effective_mappings(item, animapping)
            relevant_seasons = {
                m.season: seasons[m.season]
                for m in parsed_mappings
                if m.season in seasons
                and (
                    m.season != 0 or m.service == effective_show_ordering
                )  # Skip specials unless explicitly mapped
            }

            if not relevant_seasons:
                continue
            # Unless we're doing a full scan or destructive sync, we only want to
            # process seasons that have watched episodes
            elif not self.destructive_sync and not self.full_scan:
                any_relevant_episodes = False
                for mapping in parsed_mappings:
                    mapping_episodes = episodes_by_season.get(mapping.season, [])
                    if any(
                        (e.viewCount or e.lastViewedAt or e.lastRatedAt)
                        and e.index >= mapping.start
                        and (not mapping.end or e.index <= mapping.end)
                        for e in mapping_episodes
                    ):
                        any_relevant_episodes = True
                    else:  # No relevant episodes, remove from tracking
                        self.sync_stats.untrack_items(
                            ItemIdentifier.from_items(mapping_episodes)
                        )
                if not any_relevant_episodes:
                    continue

            try:
                anilist_media = await self.anilist_client.get_anime(
                    animapping.anilist_id
                )
            except Exception:
                log.error(
                    f"Failed to fetch AniList data for {
                        self._debug_log_title(item, animapping)
                    } "
                    f"{
                        self._debug_log_ids(
                            item.ratingKey, item.guid, guids, animapping.anilist_id
                        )
                    }",
                    exc_info=True,
                )
                continue

            if not anilist_media:
                log.warning(
                    f"No AniList entry could be found for "
                    f"{self._debug_log_title(item, animapping)} "
                    f"{self._debug_log_ids(item.ratingKey, item.guid, guids)}"
                )
                continue

            # It might be that the mapping has multiple seasons.
            # In that case, we need to find the 'primary' season to use for syncing.
            episodes: list[Episode] = []
            season_episode_counts: Counter = Counter()

            for mapping_obj in parsed_mappings:
                season_idx = mapping_obj.season
                if season_idx not in relevant_seasons:
                    continue

                season_episodes = episodes_by_season.get(season_idx, [])

                filtered_episodes = []
                if mapping_obj.end:
                    filtered_episodes = [
                        e
                        for e in season_episodes
                        if mapping_obj.start <= e.index <= mapping_obj.end
                    ]
                else:
                    filtered_episodes = [
                        e for e in season_episodes if e.index >= mapping_obj.start
                    ]

                # A negative ratio means 1 AniList episode covers multiple Plex episodes
                if mapping_obj.ratio < 0:
                    # Duplicate every episode by the ratio
                    filtered_episodes = [
                        e for e in filtered_episodes for _ in range(-mapping_obj.ratio)
                    ]
                # A positive ratio means 1 Plex episode covers multiple AniList episodes
                elif mapping_obj.ratio > 0:
                    # We include only the "representative" episodes (every ratio-th),
                    # but at the same time we need to mark the other episodes as
                    # SKIPPED to reflect that they are intentionally aggregated into
                    # another episode's mapping so coverage/logging remains accurate.
                    included: list[Episode] = []
                    suppressed: list[Episode] = []
                    for i, e in enumerate(filtered_episodes):
                        if i % mapping_obj.ratio == 0:
                            included.append(e)
                        else:
                            suppressed.append(e)
                    if suppressed:
                        with contextlib.suppress(Exception):
                            self.sync_stats.track_items(
                                ItemIdentifier.from_items(suppressed),
                                SyncOutcome.SKIPPED,
                            )
                    filtered_episodes = included

                episodes.extend(filtered_episodes)
                season_episode_counts.update({season_idx: len(filtered_episodes)})

            if not episodes:
                continue

            processed_seasons.update(season_episode_counts.keys())

            primary_season_idx = season_episode_counts.most_common(1)[0][0]
            primary_season = relevant_seasons[primary_season_idx]

            yield primary_season, episodes, animapping, anilist_media

        # We're done with the mapped seasons. Now we process the remaining seasons.
        unprocessed_seasons = set(seasons.keys()) - processed_seasons
        for index in sorted(unprocessed_seasons):
            if index < 1:
                continue  # Skip specials
            season = seasons[index]

            try:
                _anilist_media = await self.search_media(item, season)
                if not _anilist_media:
                    log.warning(
                        f"No AniList entry could be found for "
                        f"{self._debug_log_title(item)} "
                        f"{self._debug_log_ids(item.ratingKey, season.guid, guids)}"
                    )
                anilist_media = _anilist_media
            except Exception:
                log.error(
                    f"Failed to fetch AniList data for {self._debug_log_title(item)}",
                    exc_info=True,
                )
                continue

            if not anilist_media:
                _animapping = AniMap(
                    anilist_id=0,
                    tmdb_mappings={f"s{index}": ""}
                    if effective_show_ordering == "tmdb"
                    else None,
                    tvdb_mappings={f"s{index}": ""}
                    if effective_show_ordering == "tvdb"
                    else None,
                )
                log.warning(
                    f"No AniList entry could be found for "
                    f"{self._debug_log_title(item, _animapping)}"
                    f"{self._debug_log_ids(item.ratingKey, season.guid, guids)}"
                )
                continue

            episodes = episodes_by_season.get(index, [])

            animapping = AniMap(
                anilist_id=anilist_media.id,
                imdb_id=[guids.imdb] if guids.imdb else None,
                tmdb_show_id=[guids.tmdb] if guids.tmdb else None,
                tvdb_id=guids.tvdb,
                tmdb_mappings={f"s{index}": ""}
                if effective_show_ordering == "tmdb"
                else None,
                tvdb_mappings={f"s{index}": ""}
                if effective_show_ordering == "tvdb"
                else None,
            )

            yield season, episodes, animapping, anilist_media

    async def search_media(self, item: Show, child_item: Season) -> Media | None:
        """Searches for matching AniList entry by title.

        For shows, we search for entries with matching episode counts and
        similar titles (fuzzy search).

        Args:
            item (Show): Grandparent Plex media item.
            child_item (Season): Target child item to sync.

        Returns:
            Media | None: Matching AniList entry or None if not found.
        """
        if self.search_fallback_threshold == -1:
            return None
        if child_item.parentIndex == 0:
            return None

        episodes = child_item.leafCount

        results = [
            result
            async for result in self.anilist_client.search_anime(
                search_str=item.title, is_movie=False, episodes=episodes
            )
        ]
        return self._best_search_result(item.title, results)

    async def _get_all_trackable_items(self, item: Show) -> list[ItemIdentifier]:
        """Get all trackable items (episodes) for a show.

        This method collects all episodes that would potentially be processed
        during sync, following the same filtering logic as map_media() but
        without the actual mapping.

        Args:
            item (Show): Plex show item.

        Returns:
            list[ItemIdentifier]: All episode identifiers that should be tracked.
        """
        episodes = self.__get_wanted_episodes(item)
        if not episodes:
            return []

        return ItemIdentifier.from_items(episodes)

    @glru_cache(maxsize=1)
    def __get_wanted_seasons(self, item: Show) -> dict[int, Season]:
        """Get seasons that are wanted for syncing.

        Args:
            item (Show): Plex show item.

        Returns:
            dict[int, Season]: Dictionary of seasons to process.
        """
        return {
            s.index: s
            for s in item.seasons() or []
            if s is not None
            and s.leafCount  # Skip empty seasons
            and (
                self.full_scan  # We need to either be using `FULL_SCAN`
                or self.destructive_sync  # OR destructive sync
                or s.viewedLeafCount  # OR the season has been viewed
            )
        }

    @glru_cache(maxsize=1)
    def __get_wanted_episodes(self, item: Show) -> list[Episode]:
        """Get episodes that are wanted for syncing.

        Args:
            item (Show): Plex show item.

        Returns:
            list[Episode]: List of episodes to process.
        """
        seasons = self.__get_wanted_seasons(item)
        if not seasons:
            return []

        return [e for e in item.episodes() if e.parentIndex in seasons]

    async def _calculate_status(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Args:
            item (Show): Main Plex media item.
            child_item (Season): Season being processed.
            grandchild_items (list[Episode]): List of relevant episodes.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): AniMap entry with ID mappings.

        Returns:
            MediaListStatus | None: Watch status for the media item.
        """
        all_episodes = grandchild_items
        is_all_available = len(all_episodes) >= (anilist_media.episodes or sys.maxsize)

        watched_episodes = self._filter_watched_episodes(all_episodes)
        is_all_watched = len(watched_episodes) >= (
            anilist_media.episodes or sys.maxsize
        )
        is_partially_watched = len(watched_episodes) > 0

        is_online_item = self.plex_client.is_online_item(item)

        continue_watching_episode = self.plex_client.get_continue_watching(item)
        is_parent_on_continue_watching = bool(continue_watching_episode)
        is_on_continue_watching = continue_watching_episode in all_episodes

        # We've watched all episodes and are in the process of watching them again
        if is_all_watched and is_on_continue_watching:
            return MediaListStatus.REPEATING
        # We've watched all episodes
        if is_all_watched:
            return MediaListStatus.COMPLETED
        # We've watched some episodes recently and have more remaining
        if is_partially_watched and is_on_continue_watching:
            return MediaListStatus.CURRENT
        # We've not watched any episodes but the season is next up in continue watching
        if is_on_continue_watching:
            return MediaListStatus.PLANNING

        is_in_deck_window = any(
            e.lastViewedAt + self.plex_client.on_deck_window > datetime.now()
            for e in watched_episodes
            if e.lastViewedAt
        )

        # We've watched some episodes recently but the last watched episode is from a
        # different season
        if is_in_deck_window and is_parent_on_continue_watching:
            return MediaListStatus.CURRENT
        # We've watched some episodes recently and the Plex server doesn't have all
        # episodes
        if is_in_deck_window and not is_all_available:
            return MediaListStatus.CURRENT
        # We've watched some episodes recently and it's an online item, which is
        # impossible to determine the continue watching status of
        if is_in_deck_window and is_online_item:
            return MediaListStatus.CURRENT

        is_on_watchlist = self.plex_client.is_on_watchlist(item)

        # We've watched some episodes but it's no longer on continue watching.
        # However, it's on the watchlist
        if is_partially_watched and is_on_watchlist:
            return MediaListStatus.PAUSED
        # We haven't watched any episodes and it's on the watchlist
        if is_on_watchlist:
            return MediaListStatus.PLANNING
        # We've watched some episodes but it's not on continue watching or the watchlist
        if is_partially_watched:
            return MediaListStatus.DROPPED
        return None

    async def _calculate_score(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | float | None:
        """Calculates the user rating for a media item.

        Args:
            item (Show): Main Plex media item.
            child_item (Season): Specific item to sync.
            grandchild_items (list[Episode]): List of relevant episodes.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): Matched AniMap entry.

        Returns:
            int | float | None: User rating for the media item.
        """
        if all(e.userRating for e in grandchild_items):
            score = sum(e.userRating for e in grandchild_items) / len(grandchild_items)
        elif (
            sum(m.length for m in self._get_effective_mappings(item, animapping))
            == len(grandchild_items)
            == 1
        ):
            score = grandchild_items[0].userRating
        elif child_item.userRating:
            score = child_item.userRating
        elif item.userRating:
            score = item.userRating
        else:
            score = None

        return self._normalize_score(score)

    async def _calculate_progress(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the progress for a media item.

        Args:
            item (Show): Main Plex media item.
            child_item (Season): Season being processed.
            grandchild_items (list[Episode]): List of relevant episodes.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): AniMap entry with ID mappings.

        Returns:
            int | None: Progress for the media item.
        """
        watched_episodes = len(self._filter_watched_episodes(grandchild_items))
        return min(watched_episodes, anilist_media.episodes or watched_episodes)

    async def _calculate_repeats(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the number of repeats for a media item.

        Args:
            item (Show): Main Plex media item.
            child_item (Season): Season being processed.
            grandchild_items (list[Episode]): List of relevant episodes.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): AniMap entry with ID mappings.

        Returns:
            int | None: Number of repeats for the media item.
        """
        least_views = min(
            (e.viewCount for e in self._filter_watched_episodes(grandchild_items)),
            default=0,
        )
        return int(least_views - 1) if least_views else None

    async def _calculate_started_at(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Args:
            item (Show): Grandparent Plex media item.
            child_item (Season): Season being processed.
            grandchild_items (list[Episode]): List of relevant episodes.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): AniMap entry with ID mappings.

        Returns:
            FuzzyDate | None: Start date for the media item.
        """
        history = await self._filter_history_by_episodes(item, grandchild_items)
        first_history = min(history, key=lambda h: h.viewedAt) if history else None

        last_viewed_dt = min(
            (e.lastViewedAt for e in grandchild_items if e.lastViewedAt),
            default=None,
        )
        last_viewed = FuzzyDate.from_date(
            last_viewed_dt.replace(tzinfo=get_localzone()).astimezone(
                self.anilist_client.user_tz
            )
            if last_viewed_dt
            else None
        )

        history_viewed = FuzzyDate.from_date(
            first_history.viewedAt.replace(tzinfo=get_localzone()).astimezone(
                self.anilist_client.user_tz
            )
            if first_history and first_history.viewedAt
            else None
        )

        if last_viewed and history_viewed:
            return min(last_viewed, history_viewed)
        return last_viewed or history_viewed

    async def _calculate_completed_at(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Args:
            item (Show): Grandparent Plex media item.
            child_item (Season): Season being processed.
            grandchild_items (list[Episode]): List of relevant episodes.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): AniMap entry with ID mappings.

        Returns:
            FuzzyDate | None: Completion date for the media item.
        """
        history = await self._filter_history_by_episodes(item, grandchild_items)
        last_history = max(history, key=lambda h: h.viewedAt) if history else None

        last_viewed_at = max(
            (e.lastViewedAt for e in grandchild_items if e.lastViewedAt),
            default=None,
        )
        last_viewed = (
            FuzzyDate.from_date(
                last_viewed_at.replace(tzinfo=get_localzone()).astimezone(
                    self.anilist_client.user_tz
                )
            )
            if last_viewed_at
            else None
        )

        history_viewed = FuzzyDate.from_date(
            last_history.viewedAt.replace(tzinfo=get_localzone()).astimezone(
                self.anilist_client.user_tz
            )
            if last_history and last_history.viewedAt
            else None
        )

        if last_viewed and history_viewed:
            return max(last_viewed, history_viewed)
        return last_viewed or history_viewed

    async def _calculate_notes(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> str | None:
        """Chooses the most relevant user notes for a media item.

        Args:
            item (Show): Grandparent Plex media item.
            child_item (Season): Parent Plex media item.
            grandchild_items (list[Episode]): List of relevant episodes.
            anilist_media (Media): Matched AniList entry.
            animapping (AniMap): AniMap entry with ID mappings.

        Returns:
            str | None: User notes for the media item.
        """
        if len(grandchild_items) == anilist_media.episodes == 1:
            return await self.plex_client.get_user_review(grandchild_items[0])
        review = await self.plex_client.get_user_review(child_item)
        if review:
            return review
        return await self.plex_client.get_user_review(item)

    def _debug_log_title(
        self,
        item: Show,
        animapping: AniMap | None = None,
    ) -> str:
        """Creates a debug-friendly string of media titles.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            item (Show): Grandparent Plex media item.
            animapping (AniMap | None): AniMap entry for the media.

        Returns:
            Debug-friendly string of media titles.
        """
        if animapping:
            mappings = self._get_effective_mappings(item, animapping)
            mappings_str = ", ".join(str(m) for m in mappings)
        else:
            mappings_str = ""
        return (
            f"$$'{item.title} ({mappings_str})'$$"
            if mappings_str
            else f"$$'{item.title}'$$"
        )

    def _debug_log_ids(
        self,
        key: int | str,
        plex_id: str | None,
        guids: ParsedGuids,
        anilist_id: int | None = None,
    ) -> str:
        """Creates a debug-friendly string of media identifiers.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            key (int | str): Plex rating key.
            plex_id (str | None): Plex identifier.
            guids (ParsedGuids): Plex GUIDs.
            anilist_id (int | None): AniList ID.

        Returns:
            str: Debug-friendly string of media identifiers.
        """
        return (
            f"$${{key: {key}, plex_id: {plex_id}, {guids}"
            f"{f', anilist_id: {anilist_id}' if anilist_id else ''}}}$$"
        )

    @gattl_cache()
    async def _filter_history_by_episodes(
        self, item: Show, grandchild_items: list[Episode]
    ) -> list[EpisodeHistory | MovieHistory]:
        """Filters out history entries that don't exist in the grandchild items.

        Args:
            item (Show): Main Plex media item.
            grandchild_items (list[Episode]): List of relevant episodes.

        Returns:
            list[EpisodeHistory | MovieHistory]: Filtered history entries.
        """
        grandchild_rating_keys = {e.ratingKey for e in grandchild_items}
        episode_map = {e.ratingKey: e for e in grandchild_items}
        history = await self.plex_client.get_history(item)

        filtered_history: dict[int | str, EpisodeHistory | MovieHistory] = {}
        for h in history:
            if h.ratingKey in grandchild_rating_keys and (
                h.ratingKey not in filtered_history
                or h.viewedAt < filtered_history[h.ratingKey].viewedAt
            ):
                filtered_history[h.ratingKey] = h

        for rating_key, episode in episode_map.items():
            if episode.lastViewedAt and (
                rating_key not in filtered_history
                or filtered_history[rating_key].viewedAt > episode.lastViewedAt
            ):
                episode_history = EpisodeHistory(
                    server=self.plex_client.user_client._server,
                    data=episode._data,
                    initpath="/status/sessions/history/all",
                )
                episode_history.viewedAt = episode.lastViewedAt
                filtered_history[rating_key] = episode_history

        return list(filtered_history.values())

    @glru_cache(maxsize=1)
    def _filter_watched_episodes(self, episodes: list[Episode]) -> list[Episode]:
        """Filters watched episodes based on AniList entry.

        Args:
            episodes (list[Episode]): Episodes to filter.

        Returns:
            list[Episode]: Filtered episodes.
        """
        return [e for e in episodes if e.viewCount]

    def _resolve_show_ordering(self, item: Show) -> Literal["tmdb", "tvdb", ""]:
        """Return the item's preferred episode ordering."""
        if item.showOrdering:
            if item.showOrdering in ("tmdbAiring", "The Movie Database"):
                return "tmdb"
            if item.showOrdering in ("aired", "TheTVDB"):
                return "tvdb"
            return ""

        if not item.librarySectionKey:
            if getattr(item, "_source", None) == "https://metadata.provider.plex.tv":
                return "tmdb"  # The online metadata provider uses TMDB as default
            return ""  # If this happens, something weird is going on

        cached = self._show_ordering_cache.get(item.librarySectionKey)
        if cached is not None:
            return cached

        ordering_setting = next(
            (s for s in item.section().settings() if s.id == "showOrdering"), None
        )
        if not ordering_setting:
            resolved = ""
        else:
            value = ordering_setting.value
            if value in ("tmdbAiring", "The Movie Database"):
                resolved = "tmdb"
            elif value in ("aired", "TheTVDB"):
                resolved = "tvdb"
            else:
                resolved = ""

        self._show_ordering_cache[item.librarySectionKey] = resolved
        return resolved

    def _get_effective_show_ordering(
        self, item: Show, guids: ParsedGuids
    ) -> Literal["tmdb", "tvdb", ""]:
        """Determine the effective ordering used for mapping lookups.

        Preference order:
          1. Honor the library's preferred ordering if a corresponding GUID exists.
          2. Fall back to TVDB if a TVDB GUID exists.
          3. Fall back to TMDB if a TMDB GUID exists.
          4. Otherwise return empty string (no usable ordering).
        """
        preferred = self._resolve_show_ordering(item)
        if preferred == "tmdb" and guids.tmdb:
            return "tmdb"
        if preferred == "tvdb" and guids.tvdb:
            return "tvdb"
        return ""

    def _get_effective_mappings(
        self, item: Show, animapping: AniMap
    ) -> list[EpisodeMapping]:
        """Return the list of episode range mappings honoring show ordering.

        If preferred ordering mappings are not available, falls back to the other
        set of mappings.
        """
        ordering = self._resolve_show_ordering(item)
        if ordering == "tmdb" and animapping.parsed_tmdb_mappings:
            return animapping.parsed_tmdb_mappings
        elif ordering == "tvdb" and animapping.parsed_tvdb_mappings:
            return animapping.parsed_tvdb_mappings
        else:
            return animapping.parsed_tmdb_mappings or animapping.parsed_tvdb_mappings
