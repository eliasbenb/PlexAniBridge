from typing import Iterator

from plexapi.video import Movie

from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class MovieSyncClient(BaseSyncClient[Movie, Movie]):
    def map_media(
        self, item: Movie
    ) -> Iterator[tuple[Movie, AniMap | None, ParsedGuids]]:
        guids = ParsedGuids.from_guids(item.guids)
        animapping = next(
            iter(self.animap_client.get_mappings(**dict(guids), is_movie=True)), None
        )

        yield item, animapping, guids

    def search_media(self, item: Movie, *_) -> Media | None:
        results = self.anilist_client.search_anime(item.title, True, 1)
        return self._best_search_result(item.title, results)

    def _calculate_status(self, item: Movie, *_) -> MediaListStatus | None:
        is_viewed = item.viewCount > 0
        is_partially_viewed = item.viewOffset > 0
        is_on_continue_watching = self.plex_client.is_on_continue_watching(item)

        # We've already watched it and are in the process of watching it again
        if is_viewed and is_on_continue_watching:
            return MediaListStatus.REPEATING
        # We've watched it, so it's complete
        if is_viewed:
            return MediaListStatus.COMPLETED
        # We've watched part of it recently
        if is_on_continue_watching:
            return MediaListStatus.PAUSED

        is_on_watchlist = self.plex_client.is_on_watchlist(item)
        # We've watched part of it and it's not on continue watching. However, we've watchlisted it
        if is_on_watchlist and is_partially_viewed:
            return MediaListStatus.PAUSED
        # It's on our watchlist and we haven't watched it yet
        if is_on_watchlist:
            return MediaListStatus.PLANNING
        # We've watched it, but we don't want to continue watching it
        if is_partially_viewed:
            return MediaListStatus.DROPPED
        return None

    def _calculate_score(self, item: Movie, *_) -> int | None:
        return item.userRating

    def _calculate_progress(self, item: Movie, *_) -> int | None:
        return 1 if item.viewCount else None

    def _calculate_repeats(self, item: Movie, *_) -> int | None:
        return item.viewCount - 1 if item.viewCount else None

    def _calculate_started_at(self, item: Movie, *_) -> FuzzyDate | None:
        history = self.plex_client.get_first_history(item)
        if not history and not item.lastViewedAt:
            return None
        if not history:
            return FuzzyDate.from_date(item.lastViewedAt)
        if not item.lastViewedAt:
            return FuzzyDate.from_date(history.viewedAt)
        return FuzzyDate.from_date(min(history.viewedAt, item.lastViewedAt))

    def _calculate_completed_at(self, item: Movie, *_) -> FuzzyDate | None:
        return self._calculate_started_at(item, *_)
