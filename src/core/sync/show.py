import asyncio
import sys
from collections import Counter
from datetime import datetime
from typing import AsyncIterator

from plexapi.video import Episode, EpisodeHistory, MovieHistory, Season, Show
from tzlocal import get_localzone

from src import log
from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap
from src.utils.cache import generic_lru_cache

from .base import BaseSyncClient, ParsedGuids


class ShowSyncClient(BaseSyncClient[Show, Season, list[Episode]]):
    async def map_media(
        self, item: Show
    ) -> AsyncIterator[tuple[Season, list[Episode], AniMap, Media]]:
        """Maps a Plex item to potential AniList matches.

        Args:
            item (Show): Plex media item to map

        Returns:
            AsyncIterator[tuple[Season, list[Episode], AniMap, Media]]: Mapping matches (child, grandchild, animapping, anilist_media)
        """
        guids = ParsedGuids.from_guids(item.guids)

        seasons: dict[int, Season] = {
            s.index: s
            for s in item.seasons() or []
            if s is not None
            and s.leafCount  # Skip empty seasons
            and (
                self.full_scan  # We need to either be using `FULL_SCAN`
                or s.viewedLeafCount  # OR the season has been viewed
                or (item.viewedLeafCount and self.plex_client.is_online_user)
            )
        }

        if not seasons:
            return

        # Pre-fetch all episodes of the show. Instead of fetching episodes for each season
        # individually, we can fetch all episodes at once and filter them later.
        episodes_by_season: dict[int, list[Episode]] = {}
        for season_index in seasons:
            episodes_by_season[season_index] = []

        for episode in item.episodes():
            if episode.parentIndex in seasons:
                episodes_by_season.setdefault(episode.parentIndex, []).append(episode)

        all_possible_episodes = {
            str(e) for eps in episodes_by_season.values() for e in eps
        }
        self.sync_stats.possible |= all_possible_episodes

        processed_seasons: set[int] = set()

        animappings = list(
            self.animap_client.get_mappings(tvdb=guids.tvdb, is_movie=False)
        )

        for animapping in animappings:
            if not animapping.anilist_id:
                continue

            # Filter the seasons that are relevant to the current mapping
            mapped_season_indices = {m.season for m in animapping.parsed_tvdb_mappings}
            relevant_seasons = {
                idx: seasons[idx] for idx in mapped_season_indices if idx in seasons
            }

            if not relevant_seasons:
                self.sync_stats.covered |= all_possible_episodes
                continue
            elif not self.destructive_sync:
                any_relevant_episodes = False
                for mapping in animapping.parsed_tvdb_mappings:
                    mapping_episodes = episodes_by_season.get(mapping.season, [])
                    if any(
                        (e.viewCount or e.lastViewedAt or e.lastRatedAt)
                        and e.index >= mapping.start
                        and (not mapping.end or e.index <= mapping.end)
                        for e in mapping_episodes
                    ):
                        any_relevant_episodes = True
                        break
                if not any_relevant_episodes:
                    self.sync_stats.covered |= all_possible_episodes
                    continue

            try:
                anilist_media = self.anilist_client.get_anime(animapping.anilist_id)
            except Exception:
                log.error(
                    f"Failed to fetch AniList data for {self._debug_log_title(item, animapping)} "
                    f"{self._debug_log_ids(item.ratingKey, item.guid, guids, animapping.anilist_id)}",
                    exc_info=True,
                )
                self.sync_stats.failed += 1
                continue

            if not anilist_media:
                continue

            # It might be that the mapping has multiple seasons.
            # In that case, we need to find the 'primary' season to use for syncing.
            episodes: list[Episode] = []
            season_episode_counts: Counter = Counter()

            for tvdb_mapping in animapping.parsed_tvdb_mappings:
                season_idx = tvdb_mapping.season
                if season_idx not in relevant_seasons:
                    continue

                season_episodes = episodes_by_season.get(season_idx, [])

                filtered_episodes = []
                if tvdb_mapping.end:
                    filtered_episodes = [
                        e
                        for e in season_episodes
                        if tvdb_mapping.start <= e.index <= tvdb_mapping.end
                    ]
                else:
                    filtered_episodes = [
                        e for e in season_episodes if e.index >= tvdb_mapping.start
                    ]

                # A negative ratio means 1 AniList episode covers multiple Plex episodes
                if tvdb_mapping.ratio < 0:
                    # Duplicate every episode by the ratio
                    filtered_episodes = [
                        e for e in filtered_episodes for _ in range(-tvdb_mapping.ratio)
                    ]
                # A positive ratio means 1 Plex episode covers multiple AniList episodes
                elif tvdb_mapping.ratio > 0:
                    # Skip every ratio-th episode
                    tmp_episodes = {
                        e
                        for i, e in enumerate(filtered_episodes)
                        if i % tvdb_mapping.ratio == 0
                    }
                    self.sync_stats.covered |= {
                        str(e) for e in set(filtered_episodes) - tmp_episodes
                    }
                    filtered_episodes = list(tmp_episodes)

                episodes.extend(filtered_episodes)
                season_episode_counts.update({season_idx: len(filtered_episodes)})

            if not episodes:
                continue

            processed_seasons.update(season_episode_counts.keys())

            primary_season_idx = season_episode_counts.most_common(1)[0][0]
            primary_season = relevant_seasons[primary_season_idx]

            await asyncio.sleep(0)  # Add a yield point for cancellation
            yield primary_season, episodes, animapping, anilist_media

        # We're done with the mapped seasons. Now we need to process the remaining seasons.
        unprocessed_seasons = set(seasons.keys()) - processed_seasons
        for index in sorted(unprocessed_seasons):
            if index < 1:
                continue  # Skip specials
            season = seasons[index]

            try:
                _anilist_media = await self.search_media(item, season)
                if not _anilist_media:
                    continue
                anilist_media = _anilist_media
            except Exception:
                self.sync_stats.failed += 1
                log.error(
                    f"Failed to fetch AniList data for {self._debug_log_title(item)}",
                    exc_info=True,
                )
                continue

            if not anilist_media:
                log.debug(
                    f"No AniList entry could be found for "
                    f"{self._debug_log_title(item, AniMap(anilist_id=0, anidb_id=None, imdb_id=None, mal_id=None, tmdb_movie_id=None, tmdb_show_id=None, tvdb_id=None, tvdb_mappings={f's{index}': ''}))}"
                    f"{self._debug_log_ids(item.ratingKey, season.guid, guids)}"
                )
                self.sync_stats.not_found += 1
                continue

            episodes = episodes_by_season.get(index, [])

            animapping = AniMap(
                anidb_id=None,
                anilist_id=anilist_media.id,
                imdb_id=[guids.imdb] if guids.imdb else None,
                mal_id=None,
                tmdb_movie_id=None,
                tmdb_show_id=[guids.tmdb] if guids.tmdb else None,
                tvdb_id=guids.tvdb,
                tvdb_mappings={f"s{index}": ""},
            )

            await asyncio.sleep(0)  # Add a yield point for cancellation
            yield season, episodes, animapping, anilist_media

    async def search_media(self, item: Show, child_item: Season) -> Media | None:
        """Searches for matching AniList entry by title.

        For shows, we search for entries with matching episode counts and
        similar titles (fuzzy search).

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync

        Returns:
            Media | None: Matching AniList entry or None if not found
        """
        if self.search_fallback_threshold == -1:
            return None
        if child_item.parentIndex == 0:
            return None

        episodes = child_item.leafCount
        results = self.anilist_client.search_anime(
            item.title,
            is_movie=False,
            episodes=episodes,
        )
        return self._best_search_result(item.title, results)

    def _calculate_status(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Args:
            item (Show): Main Plex media item
            grandchild_items (list[Episode]): List of relevant episodes
            anilist_media (Media): Matched AniList entry

        Returns:
            MediaListStatus | None: Watch status for the media item
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
        if is_on_continue_watching:
            return MediaListStatus.CURRENT

        is_in_deck_window = any(
            e.lastViewedAt + self.plex_client.on_deck_window > datetime.now()
            for e in watched_episodes
            if e.lastViewedAt
        )

        # We've watched some episodes recently but the last watched episode is from a different season
        if is_in_deck_window and is_parent_on_continue_watching:
            return MediaListStatus.CURRENT
        # We've watched some episodes recently and the Plex server doesn't have all episodes
        if is_in_deck_window and not is_all_available:
            return MediaListStatus.CURRENT
        # We've watched some episodes recently and it's an online item, which is impossible to determine the continue watching status of
        if is_in_deck_window and is_online_item:
            return MediaListStatus.CURRENT

        is_on_watchlist = self.plex_client.is_on_watchlist(item)

        # We've watched some episodes but it's no longer on continue watching. However, it's on the watchlist
        if is_partially_watched and is_on_watchlist:
            return MediaListStatus.PAUSED
        # We haven't watched any episodes and it's on the watchlist
        if is_on_watchlist:
            return MediaListStatus.PLANNING
        # We've watched some episodes but it's not on continue watching or the watchlist
        if is_partially_watched:
            return MediaListStatus.DROPPED
        return None

    def _calculate_score(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | float | None:
        """Calculates the user rating for a media item.

        Args:
            item (Show): Main Plex media item
            child_item (Season): Specific item to sync
            grandchild_items (list[Episode]): List of relevant episodes
            animapping (AniMap): Matched AniMap entry

        Returns:
            int | float | None: User rating for the media item
        """
        if all(e.userRating for e in grandchild_items):
            score = sum(e.userRating for e in grandchild_items) / len(grandchild_items)
        elif animapping.length == len(grandchild_items) == 1:
            score = grandchild_items[0].userRating
        elif child_item.userRating:
            score = child_item.userRating
        elif item.userRating:
            score = item.userRating
        else:
            score = None

        return self._normalize_score(score)

    def _calculate_progress(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the progress for a media item.

        Args:
            grandchild_items (list[Episode]): List of relevant episodes
            anilist_media (Media): Matched AniList entry

        Returns:
            int | None: Progress for the media item
        """
        watched_episodes = len(self._filter_watched_episodes(grandchild_items))
        return min(watched_episodes, anilist_media.episodes or watched_episodes)

    def _calculate_repeats(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the number of repeats for a media item.

        Args:
            grandchild_items (list[Episode]): List of relevant episodes

        Returns:
            int | None: Number of repeats for the media item
        """
        least_views = min(
            (e.viewCount for e in self._filter_watched_episodes(grandchild_items)),
            default=0,
        )
        return int(least_views - 1) if least_views else None

    def _calculate_started_at(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Args:
            item (Show): Grandparent Plex media item
            grandchild_items (list[Episode]): List of relevant episodes

        Returns:
            FuzzyDate | None: Start date for the media item
        """
        history = self._filter_history_by_episodes(item, grandchild_items)
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

    def _calculate_completed_at(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Args:
            item (Show): Grandparent Plex media item
            grandchild_items (list[Episode]): List of relevant episodes

        Returns:
            FuzzyDate | None: Completion date for the media item
        """
        history = self._filter_history_by_episodes(item, grandchild_items)
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

    def _calculate_notes(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        *_,
        **__,
    ) -> str | None:
        """Chooses the most relevant user notes for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (Show): Grandparent Plex media item
            child_item (Season): Parent Plex media item
            grandchild_items (list[Episode]): List of relevant episodes
            anilist_media (Media): Matched AniList entry

        Returns:
            str | None: User notes for the media item
        """
        if len(grandchild_items) == anilist_media.episodes == 1:
            return self.plex_client.get_user_review(grandchild_items[0])
        return self.plex_client.get_user_review(
            child_item
        ) or self.plex_client.get_user_review(item)

    def _debug_log_title(
        self,
        item: Show,
        animapping: AniMap | None = None,
    ) -> str:
        """Creates a debug-friendly string of media titles.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            item (Show): Grandparent Plex media item
            animapping (AniMap | None): AniMap entry for the media

        Returns:
            str: Debug-friendly string of media titles
        """
        mappings_str = (
            ", ".join(str(m) for m in animapping.parsed_tvdb_mappings)
            if animapping
            else ""
        )
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
            key (int): Plex rating key
            plex_id (str): Plex ID
            guids (ParsedGuids): Plex GUIDs
            anilist_id (int | None): AniList ID

        Returns:
            str: Debug-friendly string of media identifiers
        """
        return f"$${{key: {key}, plex_id: {plex_id}, {guids}{f', anilist_id: {anilist_id}' if anilist_id else ''}}}$$"

    @generic_lru_cache(maxsize=1)
    def _filter_history_by_episodes(
        self, item: Show, grandchild_items: list[Episode]
    ) -> list[EpisodeHistory | MovieHistory]:
        """Filters out history entries that don't exist in the grandchild items.

        This function does four major tasks:
            1. Filters out history entries that don't exist in the grandchild items.
            2. Create history entries for episodes that don't have a history entry.
            3. Only includes the FIRST history entry for each episode, skipping the rest.
            4. Sorts and returns the processed history entries by the view date

        Args:
            item (Show): Main Plex media item
            grandchild_items (list[Episode]): List of relevant episodes

        Returns:
            list[EpisodeHistory]: Filtered history entries
        """
        grandchild_rating_keys = {e.ratingKey for e in grandchild_items}
        episode_map = {e.ratingKey: e for e in grandchild_items}
        history = self.plex_client.get_history(item)

        filtered_history: dict[int | str, EpisodeHistory | MovieHistory] = {}
        for h in history:
            if h.ratingKey in grandchild_rating_keys:
                if (
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

    @generic_lru_cache(maxsize=1)
    def _filter_watched_episodes(self, episodes: list[Episode]) -> list[Episode]:
        """Filters watched episodes based on AniList entry.

        Args:
            episodes (list[Episode]): Episodes to filter

        Returns:
            list[Episode]: Filtered episodes
        """
        return [e for e in episodes if e.viewCount]
