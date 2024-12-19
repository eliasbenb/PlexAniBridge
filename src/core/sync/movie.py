from typing import Iterator, Optional

from plexapi.video import Movie, MovieHistory

from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class MovieSyncClient(BaseSyncClient[Movie, Movie]):
    def map_media(self, item: Movie) -> Iterator[tuple[Movie, Optional[AniMap]]]:
        guids = ParsedGuids.from_guids(item.guids)
        animapping = self.animap_client.get_mappings(item.type, **dict(guids))
        result = next(iter(animapping), None)

        if result:
            yield item, result

    def search_media(self, item: Movie, *_) -> Optional[Media]:
        results = self.anilist_client.search_anime(item.title, True, 1)
        return self._best_search_result(item.title, results)

    def _calculate_status(self, item: Movie, *_) -> Optional[MediaListStatus]:
        if item.viewCount > 0:
            return MediaListStatus.COMPLETED
        elif item.onWatchlist():
            return MediaListStatus.PLANNING
        else:
            return None

    def _calculate_score(self, item: Movie, *_) -> int:
        return item.userRating or 0.0

    def _calculate_progress(self, item: Movie, *_) -> int:
        return 1 if item.viewCount > 0 else 0

    def _calculate_repeats(self, item: Movie, *_) -> int:
        return (item.viewCount or 1) - 1

    def _calculate_started_date(self, item: Movie, *_) -> Optional[FuzzyDate]:
        history: list[MovieHistory] = self.plex_client.get_history(
            item, max_results=1, sort_asc=True
        )
        if not history:
            return None
        return FuzzyDate.from_date(history[0].viewedAt)

    def _calculate_completed_date(self, item: Movie, *_) -> Optional[FuzzyDate]:
        return self._calculate_started_date(item)
