"""Sync client for episodic shows using provider abstractions."""

import contextlib
from collections import Counter
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from src.core.providers.library import (
    HistoryEntry,
    LibraryEpisode,
    LibrarySeason,
    LibraryShow,
)
from src.core.providers.list import ListEntry, ListMediaType, ListStatus
from src.core.sync.base import BaseSyncClient
from src.core.sync.stats import ItemIdentifier, SyncOutcome
from src.models.db.animap import AniMap, EpisodeMapping
from src.utils.cache import gattl_cache, glru_cache


class ShowSyncClient(BaseSyncClient[LibraryShow, LibrarySeason, LibraryEpisode]):
    """Synchronize show items between a library provider and a list provider."""

    async def map_media(
        self, item: LibraryShow
    ) -> AsyncIterator[
        tuple[LibrarySeason, Sequence[LibraryEpisode], AniMap | None, ListEntry]
    ]:
        """Yield mapping candidates for the provided show item."""
        seasons = self.__get_wanted_seasons(item)
        if not seasons:
            return

        episodes_by_season: dict[int, list[LibraryEpisode]] = {
            index: [] for index in seasons
        }
        for episode in self.__get_wanted_episodes(item):
            if episode.season_index in episodes_by_season:
                episodes_by_season[episode.season_index].append(episode)

        imdb_ids, tmdb_ids, tvdb_ids = self._extract_external_ids(item)
        ordering = self._get_effective_show_ordering(item, tmdb_ids, tvdb_ids)

        mappings = list(
            self.animap_client.get_mappings(
                imdb=imdb_ids or None,
                tmdb=tmdb_ids or None,
                tvdb=tvdb_ids or None,
                is_movie=False,
            )
        )

        processed_seasons: set[int] = set()

        for animapping in mappings:
            if not animapping.anilist_id:
                continue

            parsed_mappings = self._get_effective_mappings(item, animapping)
            relevant_seasons = {
                mapping.season: seasons[mapping.season]
                for mapping in parsed_mappings
                if mapping.season in seasons
                and (mapping.season != 0 or mapping.service in {ordering, ""})
            }
            if not relevant_seasons:
                continue

            if not (self.destructive_sync or self.full_scan):
                any_relevant = False
                for mapping in parsed_mappings:
                    season_episodes = episodes_by_season.get(mapping.season, [])
                    if any(
                        episode.view_count
                        and episode.index >= mapping.start
                        and (mapping.end is None or episode.index <= mapping.end)
                        for episode in season_episodes
                    ):
                        any_relevant = True
                        break
                if not any_relevant:
                    continue

            episodes: list[LibraryEpisode] = []
            episode_counts: Counter[int] = Counter()

            for mapping in parsed_mappings:
                season_index = mapping.season
                if season_index not in relevant_seasons:
                    continue

                season_episodes = episodes_by_season.get(season_index, [])
                filtered = [
                    episode
                    for episode in season_episodes
                    if episode.index >= mapping.start
                    and (mapping.end is None or episode.index <= mapping.end)
                ]

                if mapping.ratio < 0:
                    filtered = [
                        episode for episode in filtered for _ in range(-mapping.ratio)
                    ]
                elif mapping.ratio > 0 and filtered:
                    included: list[LibraryEpisode] = []
                    suppressed: list[LibraryEpisode] = []
                    for idx, episode in enumerate(filtered):
                        if idx % mapping.ratio == 0:
                            included.append(episode)
                        else:
                            suppressed.append(episode)
                    if suppressed:
                        with contextlib.suppress(Exception):
                            self.sync_stats.track_items(
                                ItemIdentifier.from_items(suppressed),
                                SyncOutcome.SKIPPED,
                            )
                    filtered = included

                episodes.extend(filtered)
                episode_counts.update({season_index: len(filtered)})

            if not episodes:
                continue

            try:
                entry = await self.list_provider.get_entry(str(animapping.anilist_id))
            except Exception:
                continue
            if entry is None:
                continue

            processed_seasons.update(episode_counts.keys())
            primary_season_index = episode_counts.most_common(1)[0][0]
            primary_season = relevant_seasons[primary_season_index]

            yield primary_season, tuple(episodes), animapping, entry

        remaining_seasons = sorted(set(seasons) - processed_seasons)
        for season_index in remaining_seasons:
            if season_index < 1:
                continue
            season = seasons[season_index]
            entry = await self.search_media(item, season)
            if entry is None:
                continue
            episodes = list(episodes_by_season.get(season_index, []))
            if not episodes:
                continue
            yield season, episodes, None, entry

    async def search_media(
        self, item: LibraryShow, child_item: LibrarySeason
    ) -> ListEntry | None:
        """Locate a fallback list entry for the given season."""
        if self.search_fallback_threshold < 0 or child_item.index == 0:
            return None

        results = await self.list_provider.search(item.title)
        tv_results = [
            entry for entry in results if entry.media().media_type == ListMediaType.TV
        ]
        episode_count = len(child_item.episodes())
        filtered = [
            entry
            for entry in tv_results
            if entry.total_units is None or entry.total_units == episode_count
        ]
        candidates = filtered or tv_results
        return self._best_search_result(item.title, candidates)

    @gattl_cache(ttl=15, key=lambda self, item: item)
    async def _get_all_trackable_items(self, item: LibraryShow) -> list[ItemIdentifier]:
        episodes = self.__get_wanted_episodes(item)
        if not episodes:
            return []
        return list(ItemIdentifier.from_items(episodes))

    async def _calculate_status(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> ListStatus | None:
        watched_count = len(
            [episode for episode in grandchild_items if episode.view_count]
        )
        min_view_count = min(
            (episode.view_count for episode in grandchild_items if episode.view_count),
            default=0,
        )
        on_watching = item.on_watching and any(
            episode.on_watching for episode in grandchild_items
        )  # Check item.on_watching first to pre-filter unwatched shows (perf)
        is_finished = (
            entry.total_units is not None and watched_count >= entry.total_units
        )

        if is_finished:
            if on_watching and min_view_count >= 1:
                return ListStatus.REPEATING
            return ListStatus.COMPLETED

        if on_watching:
            return ListStatus.CURRENT

        if watched_count:
            if item.on_watchlist or child_item.on_watchlist:
                return ListStatus.PAUSED
            return ListStatus.DROPPED

        if item.on_watchlist or child_item.on_watchlist:
            return ListStatus.PLANNING

        return None

    async def _calculate_score(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        scores = [
            episode.user_rating for episode in grandchild_items if episode.user_rating
        ]
        if scores:
            return round(sum(scores) / len(scores))
        if child_item.user_rating:
            return child_item.user_rating
        if item.user_rating:
            return item.user_rating
        return None

    async def _calculate_progress(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        watched = len([episode for episode in grandchild_items if episode.view_count])
        total_units = entry.total_units or len(grandchild_items)
        if total_units:
            return min(watched, total_units)
        return watched or None

    async def _calculate_repeats(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        view_counts = [
            episode.view_count for episode in grandchild_items if episode.view_count
        ]
        return min(view_counts) - 1 if view_counts else None

    async def _calculate_started_at(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> datetime | None:
        history = await self._filter_history_by_episodes(item, grandchild_items)
        if not history:
            return None
        return min(record.viewed_at for record in history)

    async def _calculate_completed_at(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> datetime | None:
        history = await self._filter_history_by_episodes(item, grandchild_items)
        if not history:
            return None
        return max(record.viewed_at for record in history)

    async def _calculate_notes(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> str | None:
        for episode in grandchild_items:
            review = await episode.review()
            if review:
                return review
        review = await child_item.review()
        if review:
            return review
        return await item.review()

    def _debug_log_title(
        self, item: LibraryShow, animapping: AniMap | None = None
    ) -> str:
        if animapping:
            mappings = self._get_effective_mappings(item, animapping)
            mapping_str = ", ".join(str(mapping) for mapping in mappings)
            if mapping_str:
                return f"$$'{item.title} ({mapping_str})'$$"
        return f"$$'{item.title}'$$"

    def _debug_log_ids(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> str:
        ids = ", ".join(repr(external) for external in item.ids())
        ids = ids or "none"
        return (
            f"$${{library_key: {child_item.key}, media_key: {entry.media().key}"
            + f", {ids}}}$$"
            if ids
            else ""
        )

    def _extract_external_ids(
        self, item: LibraryShow
    ) -> tuple[list[str], list[int], list[int]]:
        imdb_ids: list[str] = []
        tmdb_ids: list[int] = []
        tvdb_ids: list[int] = []
        for external in item.ids():
            namespace = external.namespace.lower()
            if namespace == "imdb":
                imdb_ids.append(external.value)
            elif namespace == "tmdb":
                with contextlib.suppress(ValueError):
                    tmdb_ids.append(int(external.value))
            elif namespace == "tvdb":
                with contextlib.suppress(ValueError):
                    tvdb_ids.append(int(external.value))
        return imdb_ids, tmdb_ids, tvdb_ids

    @glru_cache(maxsize=32, key=lambda self, item: item)
    def __get_wanted_seasons(self, item: LibraryShow) -> dict[int, LibrarySeason]:
        seasons: dict[int, LibrarySeason] = {}
        for season in item.seasons():
            episodes = season.episodes()
            if not episodes:
                continue
            if (
                self.full_scan
                or self.destructive_sync
                or any(episode.view_count for episode in episodes)
            ):
                seasons[season.index] = season
        return seasons

    @glru_cache(maxsize=32, key=lambda self, item: item)
    def __get_wanted_episodes(self, item: LibraryShow) -> list[LibraryEpisode]:
        seasons = self.__get_wanted_seasons(item)
        if not seasons:
            return []
        return [
            episode for episode in item.episodes() if episode.season_index in seasons
        ]

    @gattl_cache(ttl=15, key=lambda self, item, episodes: (item, tuple(episodes)))
    async def _filter_history_by_episodes(
        self, item: LibraryShow, episodes: Sequence[LibraryEpisode]
    ) -> list[HistoryEntry]:
        episode_keys = {episode.key for episode in episodes}
        history = await item.history()
        filtered = [entry for entry in history if entry.media_key in episode_keys]
        seen_keys = {entry.media_key for entry in filtered}

        for episode in episodes:
            if episode.key in seen_keys:
                continue
            episode_history = await episode.history()
            for entry in episode_history:
                if entry.media_key == episode.key:
                    filtered.append(entry)
                    seen_keys.add(episode.key)
                    break

        filtered.sort(key=lambda record: record.viewed_at)
        return filtered

    @glru_cache(maxsize=32, key=lambda self, item, tmdb_ids, tvdb_ids: item)
    def _get_effective_show_ordering(
        self,
        item: LibraryShow,
        tmdb_ids: Sequence[int],
        tvdb_ids: Sequence[int],
    ) -> str:
        if item.ordering == "tvdb" and tvdb_ids:
            return "tvdb"
        if item.ordering == "tmdb" and tmdb_ids:
            return "tmdb"
        if tvdb_ids:
            return "tvdb"
        if tmdb_ids:
            return "tmdb"
        return ""

    def _get_effective_mappings(
        self, item: LibraryShow, animapping: AniMap
    ) -> list[EpisodeMapping]:
        if item.ordering == "tmdb" and animapping.parsed_tmdb_mappings:
            return animapping.parsed_tmdb_mappings
        if item.ordering == "tvdb" and animapping.parsed_tvdb_mappings:
            return animapping.parsed_tvdb_mappings
        return animapping.parsed_tmdb_mappings or animapping.parsed_tvdb_mappings
