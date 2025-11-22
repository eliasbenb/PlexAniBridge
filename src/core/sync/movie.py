"""Sync client for library movies using provider abstractions."""

import contextlib
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from src.core.providers.library import LibraryMovie
from src.core.providers.list import ListEntry, ListMediaType, ListStatus
from src.core.sync.base import BaseSyncClient
from src.core.sync.stats import ItemIdentifier
from src.models.db.animap import AniMap


class MovieSyncClient(BaseSyncClient[LibraryMovie, LibraryMovie, LibraryMovie]):
    """Synchronize movie items between a library provider and a list provider."""

    async def map_media(
        self, item: LibraryMovie
    ) -> AsyncIterator[
        tuple[LibraryMovie, Sequence[LibraryMovie], AniMap | None, ListEntry]
    ]:
        """Map a library movie to its corresponding list entry."""
        imdb_ids, tmdb_ids, tvdb_ids = self._extract_external_ids(item)
        mappings = list(
            self.animap_client.get_mappings(
                imdb=imdb_ids or None,
                tmdb=tmdb_ids or None,
                tvdb=tvdb_ids or None,
                is_movie=True,
            )
        )

        for mapping in mappings:
            if not mapping.anilist_id:
                continue
            try:
                entry = await self.list_provider.get_entry(str(mapping.anilist_id))
            except Exception:
                continue

            yield item, (item,), mapping, entry
            return

        entry = await self.search_media(item, item)
        if entry is not None:
            yield item, (item,), None, entry

    async def search_media(
        self, item: LibraryMovie, child_item: LibraryMovie
    ) -> ListEntry | None:
        """Fallback search for matching list entries."""
        if self.search_fallback_threshold < 0:
            return None

        results = await self.list_provider.search(item.title)
        movie_results = [
            entry
            for entry in results
            if entry.media().media_type == ListMediaType.MOVIE
        ]
        return self._best_search_result(item.title, movie_results)

    async def _get_all_trackable_items(
        self, item: LibraryMovie
    ) -> list[ItemIdentifier]:
        return [ItemIdentifier.from_item(item)]

    async def _calculate_status(
        self,
        *,
        item: LibraryMovie,
        child_item: LibraryMovie,
        grandchild_items: Sequence[LibraryMovie],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> ListStatus | None:
        has_views = item.view_count > 0
        history = await item.history()
        has_history = bool(history)

        if has_views and item.on_watching:
            return ListStatus.REPEATING
        if has_views:
            return ListStatus.COMPLETED
        if item.on_watching:
            return ListStatus.CURRENT
        if item.on_watchlist:
            return ListStatus.PLANNING
        if has_history:
            return ListStatus.DROPPED
        return None

    async def _calculate_score(
        self,
        *,
        item: LibraryMovie,
        child_item: LibraryMovie,
        grandchild_items: Sequence[LibraryMovie],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        return item.user_rating

    async def _calculate_progress(
        self,
        *,
        item: LibraryMovie,
        child_item: LibraryMovie,
        grandchild_items: Sequence[LibraryMovie],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        total_units = entry.total_units or len(grandchild_items) or 1
        return total_units if item.view_count > 0 else None

    async def _calculate_repeats(
        self,
        *,
        item: LibraryMovie,
        child_item: LibraryMovie,
        grandchild_items: Sequence[LibraryMovie],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        return item.view_count - 1 if item.view_count > 0 else None

    async def _calculate_started_at(
        self,
        *,
        item: LibraryMovie,
        child_item: LibraryMovie,
        grandchild_items: Sequence[LibraryMovie],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> datetime | None:
        history = await item.history()
        if not history:
            return None
        return min(record.viewed_at for record in history)

    async def _calculate_completed_at(
        self,
        *,
        item: LibraryMovie,
        child_item: LibraryMovie,
        grandchild_items: Sequence[LibraryMovie],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> datetime | None:
        history = await item.history()
        if not history:
            return None
        return max(record.viewed_at for record in history)

    async def _calculate_notes(
        self,
        *,
        item: LibraryMovie,
        child_item: LibraryMovie,
        grandchild_items: Sequence[LibraryMovie],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> str | None:
        return await item.review()

    def _debug_log_title(
        self, item: LibraryMovie, animapping: AniMap | None = None
    ) -> str:
        return f"$$'{item.title}'$$"

    def _debug_log_ids(
        self,
        *,
        item: LibraryMovie,
        child_item: LibraryMovie,
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
        self, item: LibraryMovie
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
