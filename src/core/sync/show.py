from typing import Iterator, Optional

from plexapi.video import Episode, EpisodeHistory, Season, Show

from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class ShowSyncClient(BaseSyncClient[Show, Season]):
    def map_media(self, item: Show) -> Iterator[tuple[Season, Optional[AniMap]]]:
        guids = ParsedGuids.from_guids(item.guids)
        seasons: list[Season] = item.seasons(index__gt=0)
        season_map = {s.index: s for s in seasons}

        for animapping in self.animap_client.get_mappings(item.type, **dict(guids)):
            if animapping.tvdb_season is None:
                continue
            if animapping.tvdb_season in season_map:
                yield season_map.pop(animapping.tvdb_season), animapping

        for season in season_map.values():
            yield season, None

    def search_media(self, item: Show, subitem: Season) -> Optional[Media]:
        episodes = subitem.leafCount
        results = self.anilist_client.search_anime(item.title, False, episodes)
        return self._best_search_result(item.title, results)

    def _calculate_status(
        self,
        item: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> Optional[MediaListStatus]:
        watched_episodes = self.__filter_watched_episodes(
            item, subitem, anilist_media, animapping
        )

        if len(watched_episodes) >= anilist_media.episodes:
            return MediaListStatus.COMPLETED
        elif len(watched_episodes) > 1:
            return MediaListStatus.CURRENT
        elif item.onWatchlist():
            return MediaListStatus.PLANNING
        else:
            return None

    def _calculate_score(self, item: Show, subitem: Season, *_) -> int:
        return subitem.userRating or item.userRating or 0.0

    def _calculate_progress(
        self,
        item: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> int:
        return len(
            self.__filter_watched_episodes(item, subitem, anilist_media, animapping)
        )

    def _calculate_repeats(
        self,
        item: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> int:
        episodes = self.__filter_mapped_episodes(
            item, subitem, anilist_media, animapping
        )
        return (min((e.viewCount for e in episodes), default=1) or 1) - 1

    def _calculate_started_date(
        self,
        _: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> Optional[FuzzyDate]:
        history: list[EpisodeHistory] = [
            h
            for h in self.plex_client.get_history(subitem, sort_asc=True)
            if h.index > animapping.tvdb_epoffset
            and h.index <= animapping.tvdb_epoffset + anilist_media.episodes
        ]
        if history:
            return FuzzyDate.from_date(history[0].viewedAt)
        else:
            return None

    def _calculate_completed_date(
        self,
        _: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> Optional[FuzzyDate]:
        history = [
            h
            for h in self.plex_client.get_history(subitem, sort_asc=False)
            if animapping.tvdb_epoffset
            < h.index
            <= animapping.tvdb_epoffset + anilist_media.episodes
        ]

        deduplicated_history = {
            h.ratingKey: max(
                filter(lambda x: x.ratingKey == h.ratingKey, history),
                key=lambda x: x.viewedAt,
            )
            for h in history
        }

        return (
            FuzzyDate.from_date(min(h.viewedAt for h in deduplicated_history.values()))
            if deduplicated_history
            else None
        )

    def __filter_mapped_episodes(
        self,
        _: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> list[Episode]:
        return subitem.episodes(
            index__gt=animapping.tvdb_epoffset,
            index__lte=animapping.tvdb_epoffset + anilist_media.episodes,
        )

    def __filter_watched_episodes(
        self,
        _: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> list[Episode]:
        return subitem.episodes(
            index__gt=animapping.tvdb_epoffset,
            index__lte=animapping.tvdb_epoffset + anilist_media.episodes,
            viewCount__gt=0,
        )
