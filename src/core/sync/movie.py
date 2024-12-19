from typing import Iterator, Optional

from plexapi.video import Movie, MovieHistory

from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class MovieSyncClient(BaseSyncClient[Movie, Movie]):
    def map_media(self, item: Movie) -> Iterator[tuple[Movie, Optional[AniMap]]]:
        guids = ParsedGuids.from_guids(item.guids)

        animappings = self.animap_client.get_mappings(**dict(guids), is_movie=True)
        animapping = next(iter(animappings), None)
        if not animappings:
            yield item, None
            return

        if guids.imdb and animapping.imdb_id:
            try:
                idx = animapping.imdb_id.index(guids.imdb)
                animapping.anilist_id = (
                    [animapping.anilist_id[idx]] if animapping.anilist_id else None
                )
                animapping.mal_id = (
                    [animapping.mal_id[idx]] if animapping.mal_id else None
                )
            except (ValueError, IndexError):
                pass

        yield item, animapping

    def search_media(self, item: Movie, *_) -> Optional[Media]:
        results = self.anilist_client.search_anime(item.title, True, 1)
        return self._best_search_result(item.title, results)

    def _calculate_status(self, item: Movie, *_) -> Optional[MediaListStatus]:
        is_viewed = item.viewCount > 0
        is_partially_viewed = item.viewOffset > 0
        is_on_continue_watching = self.plex_client.get_continue_watching(item) and True
        is_on_watchlist = item.onWatchlist()

        # We've already watched it and are in the process of watching it again
        if is_viewed and is_on_continue_watching:
            return MediaListStatus.REPEATING
        # We've watched it, so it's complete
        if is_viewed:
            return MediaListStatus.COMPLETED
        # We've watched part of it recently
        if is_on_continue_watching:
            return MediaListStatus.PAUSED
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

    def _calculate_score(self, item: Movie, *_) -> int:
        return item.userRating or 0.0

    def _calculate_progress(self, item: Movie, *_) -> int:
        return 1 if item.viewCount > 0 else 0

    def _calculate_repeats(self, item: Movie, *_) -> int:
        return (item.viewCount or 1) - 1

    def _calculate_started_at(self, item: Movie, *_) -> Optional[FuzzyDate]:
        history: list[MovieHistory] = self.plex_client.get_history(
            item, max_results=1, sort_asc=True
        )
        if not history:
            return None
        return FuzzyDate.from_date(history[0].viewedAt)

    def _calculate_completed_at(self, item: Movie, *_) -> Optional[FuzzyDate]:
        return self._calculate_started_at(item)
