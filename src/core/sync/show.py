from typing import Iterator, Optional

import plexapi.exceptions
from plexapi.video import Episode, EpisodeHistory, Season, Show

from src.models.anilist import FuzzyDate, Media, MediaListStatus, MediaStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class ShowSyncClient(BaseSyncClient[Show, Season]):
    def map_media(self, item: Show) -> Iterator[tuple[Season, Optional[AniMap]]]:
        guids = ParsedGuids.from_guids(item.guids)
        seasons: list[Season] = item.seasons()
        season_map = {s.index: s for s in seasons}

        for animapping in self.animap_client.get_mappings(
            **dict(guids), is_movie=False
        ):
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
        all_episodes = self.__filter_mapped_episodes(
            item, subitem, anilist_media, animapping
        )
        watched_episodes = self.__filter_watched_episodes(
            item, subitem, anilist_media, animapping
        )
        countinue_watching_episodes = self.plex_client.get_continue_watching(
            subitem,
            season_lower=animapping.tvdb_epoffset + 1,
            season_upper=animapping.tvdb_epoffset + anilist_media.episodes,
        )

        is_viewed = len(watched_episodes) >= anilist_media.episodes
        is_partially_viewed = len(watched_episodes) > 0
        is_on_continue_watching = len(countinue_watching_episodes) > 0
        is_on_watchlist = item.onWatchlist()

        # We've watched it and are in the process of watching it again
        if is_viewed and is_on_continue_watching:
            return MediaListStatus.REPEATING
        if is_viewed:
            return MediaListStatus.COMPLETED
        # We've watched some episode recently and have more remaining
        if is_on_continue_watching:
            return MediaListStatus.CURRENT
        # We've watched all currently aired episodes, which is why it's not on continue watching
        if (
            anilist_media.status == MediaStatus.RELEASING
            and len(watched_episodes) == len(all_episodes)
            and is_partially_viewed
        ):
            return MediaListStatus.CURRENT
        # We've watched all the episodes available to us, so we're forced to pause
        if len(all_episodes) == len(watched_episodes) and is_partially_viewed:
            return MediaListStatus.PAUSED
        # At this point, we can consider the show dropped. However, if it is on the watchlist, we'll assume the user still wants to watch it
        if is_on_watchlist and is_partially_viewed:
            return MediaListStatus.PAUSED
        # On the watchlist + no partial views = planning
        if is_on_watchlist:
            return MediaListStatus.PLANNING
        # We've watched some episodes but are not on continue watching, so we're dropped
        if is_partially_viewed:
            return MediaListStatus.DROPPED
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

    def _calculate_started_at(
        self,
        _: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> Optional[FuzzyDate]:
        try:
            episode = subitem.get(episode=animapping.tvdb_epoffset + 1)
            history: EpisodeHistory = self.plex_client.get_history(
                episode, max_results=1, sort_asc=True
            )[0]
        except (plexapi.exceptions.NotFound, IndexError):
            return None

        return FuzzyDate.from_date(history.viewedAt)

    def _calculate_completed_at(
        self,
        _: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> Optional[FuzzyDate]:
        try:
            episode = subitem.get(
                episode=animapping.tvdb_epoffset + anilist_media.episodes
            )
            history: EpisodeHistory = self.plex_client.get_history(
                episode, max_results=1, sort_asc=True
            )[0]
        except (plexapi.exceptions.NotFound, IndexError):
            return None

        return FuzzyDate.from_date(history.viewedAt)

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
