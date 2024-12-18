from typing import Iterator, Optional

from plexapi.video import Movie

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

    def _calculate_status(
        self,
        item: Movie,
        subitem: Movie,
        anilist_media: Media,
        animapping: AniMap,
    ) -> Optional[MediaListStatus]:
        if item.viewCount > 0:
            return MediaListStatus.COMPLETED
        elif item.onWatchlist():
            return MediaListStatus.PLANNING
        else:
            return None

    def _calculate_score(
        self, item: Movie, subitem: Movie, anilist_media: Media, animapping: AniMap
    ) -> int:
        return item.userRating or 0.0

    def _calculate_progress(
        self,
        item: Movie,
        subitem: Movie,
        anilist_media: Media,
        animapping: AniMap,
    ) -> int:
        return 1 if item.viewCount > 0 else 0

    def _calculate_repeats(
        self,
        item: Movie,
        subitem: Movie,
        anilist_media: Media,
        animapping: AniMap,
    ) -> int:
        return (item.viewCount or 1) - 1

    def _calculate_started_date(
        self,
        item: Movie,
        subitem: Movie,
        anilist_media: Media,
        animapping: AniMap,
    ) -> Optional[Media]:
        return FuzzyDate.from_date(item.lastViewedAt) if item.lastViewedAt else None

    def _calculate_completed_date(
        self,
        item: Movie,
        subitem: Movie,
        anilist_media: Media,
        animapping: AniMap,
    ) -> Optional[Media]:
        return FuzzyDate.from_date(item.lastViewedAt) if item.lastViewedAt else None
