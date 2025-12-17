"""Sync client for episodic shows using provider abstractions."""

from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from anibridge.library import (
    HistoryEntry,
    LibraryEpisode,
    LibrarySeason,
    LibraryShow,
)
from anibridge.list import ListEntry, ListMediaType, ListStatus
from anibridge.list import MappingGraph as ListMappingGraph

from src.core.animap import MappingGraph
from src.core.sync.base import BaseSyncClient
from src.core.sync.stats import ItemIdentifier
from src.utils.cache import gattl_cache, glru_cache

__all__ = ["ShowSyncClient"]


@dataclass(slots=True)
class _SeasonGroup:
    child_item: LibrarySeason
    first_index: int
    episodes: list[LibraryEpisode]
    entry: ListEntry | None
    mapping: MappingGraph | None
    media_key: str


class ShowSyncClient(BaseSyncClient[LibraryShow, LibrarySeason, LibraryEpisode]):
    """Synchronize show items between a library provider and a list provider."""

    async def map_media(
        self, item: LibraryShow
    ) -> AsyncIterator[
        tuple[
            LibrarySeason,
            Sequence[LibraryEpisode],
            MappingGraph | None,
            ListEntry | None,
            str | None,
        ]
    ]:
        """Yield mapping candidates for the provided show item."""
        seasons = self.__get_wanted_seasons(item)
        if not seasons:
            return

        wanted_indexes = set(seasons)
        episodes_by_season: dict[int, list[LibraryEpisode]] = defaultdict(list)
        for ep in self.__get_wanted_episodes(item):
            if ep.season_index in wanted_indexes:
                episodes_by_season[ep.season_index].append(ep)

        mapping_graph = self.animap_client.get_graph_for_ids(item.ids())
        entry_cache: dict[str, ListEntry | None] = {}

        async def get_entry_cached(key: str) -> ListEntry | None:
            """Retrieve a list entry from cache or provider."""
            if (cached := entry_cache.get(key, ...)) is not ...:
                return cached
            try:
                entry = await self.list_provider.get_entry(key)
            except Exception:
                entry = None
            entry_cache[key] = entry
            return entry

        def resolve_key(scope: str) -> tuple[str | None, bool]:
            """Attempt to resolve a media key for the given scope."""
            if (
                r := self.list_provider.resolve_mappings(
                    cast(ListMappingGraph, mapping_graph), scope=scope
                )
            ) is not None:
                return str(r), True
            return None, False

        async def resolve_season(
            season_index: int, season: LibrarySeason
        ) -> tuple[str | None, ListEntry | None, MappingGraph | None]:
            """Resolve a media key and list entry for the given season."""
            key, mapped = resolve_key(f"s{season_index}")
            if key:
                entry = await get_entry_cached(key)
                return key, entry, (mapping_graph if mapped else None)

            entry = await self.search_media(item, season)
            if not entry:
                return None, None, None

            key = str(entry.media().key)
            entry_cache[key] = entry
            return key, entry, None

        groups: dict[str, _SeasonGroup] = {}

        for season_index in sorted(wanted_indexes):
            season = seasons[season_index]
            season_episodes = episodes_by_season.get(season_index)
            if not season_episodes:
                continue

            key, entry, mapping = await resolve_season(season_index, season)
            if not key:
                continue

            media_key = entry.media().key if entry else key
            if (group := groups.get(key)) is None:
                groups[key] = _SeasonGroup(
                    child_item=season,
                    first_index=season_index,
                    episodes=list(season_episodes),
                    entry=entry,
                    mapping=mapping,
                    media_key=media_key,
                )
                continue

            if season_index < group.first_index:
                group.child_item, group.first_index = season, season_index
            group.episodes.extend(season_episodes)
            group.entry = entry or group.entry
            group.mapping = group.mapping or mapping

        for group in sorted(groups.values(), key=lambda g: g.first_index):
            eps = sorted(group.episodes, key=lambda ep: (ep.season_index, ep.index))
            yield (
                group.child_item,
                tuple(eps),
                group.mapping,
                group.entry,
                group.media_key,
            )

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
        mapping: MappingGraph | None,
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
        )
        is_finished = (
            entry.total_units is not None and watched_count >= entry.total_units
        ) or (entry.total_units is None and watched_count >= len(grandchild_items))

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

    async def _calculate_user_rating(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        mapping: MappingGraph | None,
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
        mapping: MappingGraph | None,
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
        mapping: MappingGraph | None,
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
        mapping: MappingGraph | None,
    ) -> datetime | None:
        history = await self._filter_history_by_episodes(item, grandchild_items)
        if not history:
            return None
        return min(record.viewed_at for record in history)

    async def _calculate_finished_at(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        mapping: MappingGraph | None,
    ) -> datetime | None:
        history = await self._filter_history_by_episodes(item, grandchild_items)
        if not history:
            return None
        return max(record.viewed_at for record in history)

    async def _calculate_review(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        grandchild_items: Sequence[LibraryEpisode],
        entry: ListEntry,
        mapping: MappingGraph | None,
    ) -> str | None:
        if entry.total_units == 1 and len(grandchild_items) == 1:
            review = await grandchild_items[0].review()
            if review:
                return review
        return await child_item.review() or await item.review()

    def _derive_scope(
        self, *, item: LibraryShow, child_item: LibrarySeason | None
    ) -> str | None:
        return f"s{child_item.index}" if child_item is not None else None

    def _debug_log_title(
        self,
        item: LibraryShow,
        mapping: MappingGraph | None = None,
        media_key: str | None = None,
    ) -> str:
        return f"$$'{item.title}'$$"

    def _debug_log_ids(
        self,
        *,
        item: LibraryShow,
        child_item: LibrarySeason,
        entry: ListEntry | None,
        mapping: MappingGraph | None,
        media_key: str | None,
    ) -> str:
        if not media_key and mapping is not None:
            media_key = self.list_provider.resolve_mappings(
                mapping, scope=f"s{child_item.index}"
            )
        if not media_key and entry is not None:
            media_key = entry.media().key
        ids = {"library_key": child_item.key, "list_key": media_key, **item.ids()}
        return self._format_external_ids(ids)

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
        filtered = [entry for entry in history if entry.library_key in episode_keys]
        filtered.sort(key=lambda record: record.viewed_at)
        return filtered
