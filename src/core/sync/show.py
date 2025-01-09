import sys
from typing import Iterator

import plexapi.exceptions
from plexapi.video import Episode, Season, Show

from src.models.anilist import FuzzyDate, Media, MediaListStatus, MediaStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class ShowSyncClient(BaseSyncClient[Show, Season]):
    def map_media(
        self, item: Show
    ) -> Iterator[tuple[Season, AniMap | None, ParsedGuids]]:
        """Maps a Plex item to potential AniList matches.

        For shows, we map each season to its corresponding AniList entry.

        Args:
            item (Show): Plex media item to map

        Returns:
            Iterator[tuple[S, AniMap | None]]: Potential matches
        """
        guids = ParsedGuids.from_guids(item.guids)
        season_map: dict[int, Season] = {
            s.index: s
            for s in item.seasons()
            if self.destructive_sync or s.viewedLeafCount > 0
        }
        unyielded_seasons = set(season_map.keys())

        for animapping in self.animap_client.get_mappings(
            **dict(guids), is_movie=False
        ):
            if animapping.tvdb_season is None:
                continue
            if animapping.tvdb_season in season_map:
                try:
                    unyielded_seasons.remove(animapping.tvdb_season)
                except KeyError:
                    pass
                yield season_map[animapping.tvdb_season], animapping, guids

        for season in unyielded_seasons:
            yield season_map[season], None, guids

    def search_media(self, item: Show, subitem: Season) -> Media | None:
        """Searches for matching AniList entry by title.

        For shows, we search for entries with matching episode counts and
        similar titles (fuzzy search).

        Args:
            item (Show): Main Plex item
            subitem (Season): Specific item to match

        Returns:
            Media | None: Matching AniList entry or None if not found
        """
        if subitem.seasonNumber == 0:
            return None
        episodes = subitem.leafCount
        results = self.anilist_client.search_anime(item.title, False, episodes)
        return self._best_search_result(item.title, results)

    def _calculate_status(
        self,
        item: Show,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
    ) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Args:
            item (Show): Main Plex media item
            subitem (Season): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            MediaListStatus | None: Watch status for the media item
        """
        watched_episodes = self.__filter_watched_episodes(
            subitem, anilist_media, animapping
        )
        is_viewed = len(watched_episodes) >= (anilist_media.episodes or sys.maxsize)
        is_partially_viewed = len(watched_episodes) > 0
        is_on_continue_watching = self.plex_client.is_on_continue_watching(
            subitem,
            index__gt=animapping.tvdb_epoffset,
            index__lte=animapping.tvdb_epoffset
            + (anilist_media.episodes or sys.maxsize),
        )

        # We've watched it and are in the process of watching it again
        if is_viewed and is_on_continue_watching:
            return MediaListStatus.REPEATING
        if is_viewed:
            return MediaListStatus.COMPLETED
        # We've watched some episode recently and have more remaining
        if is_on_continue_watching:
            return MediaListStatus.CURRENT

        all_episodes = self.__filter_mapped_episodes(subitem, anilist_media, animapping)
        # We've watched all episodes available to us
        if len(watched_episodes) == len(all_episodes) and is_partially_viewed:
            return MediaListStatus.CURRENT

        is_on_watchlist = self.plex_client.is_on_watchlist(item)
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

    def _calculate_score(self, item: Show, subitem: Season, **_) -> int | None:
        """Calculates the user rating for a media item.

        Args:
            item (Show): Main Plex media item
            subitem (Season): Specific item to sync

        Returns:
            int | None: User rating for the media item
        """
        return subitem.userRating or item.userRating

    def _calculate_progress(
        self,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
        **_,
    ) -> int | None:
        """Calculates the progress for a media item.

        Args:
            subitem (Season): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: Progress for the media item
        """
        return (
            len(self.__filter_watched_episodes(subitem, anilist_media, animapping))
            or None
        )

    def _calculate_repeats(
        self,
        subitem: Season,
        anilist_media: Media,
        animapping: AniMap,
        **_,
    ) -> int | None:
        """Calculates the number of repeats for a media item.

        Args:
            subitem (Season): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: Number of repeats for the media item
        """
        episodes = self.__filter_mapped_episodes(subitem, anilist_media, animapping)
        least_views = min((e.viewCount for e in episodes), default=0)
        return least_views - 1 if least_views else None

    def _calculate_started_at(
        self, subitem: Season, animapping: AniMap, **_
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Args:
            subitem (Movie): Specific item to sync
            animapping (AniMap): ID mapping information

        Returns:
            FuzzyDate | None: Start date for the media item
        """
        try:
            episode: Episode = subitem.get(episode=animapping.tvdb_epoffset + 1)
        except (plexapi.exceptions.NotFound, IndexError):
            return None

        history = self.plex_client.get_first_history(episode)
        if not history and not episode.lastViewedAt:
            return None
        if not history:
            return FuzzyDate.from_date(episode.lastViewedAt)

        return min(
            FuzzyDate.from_date(history.viewedAt) or 0,
            FuzzyDate.from_date(episode.lastViewedAt) or 0,
        )

    def _calculate_completed_at(
        self, subitem: Season, anilist_media: Media, animapping: AniMap, **_
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Args:
            subitem (Movie): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            FuzzyDate | None: Completion date for the media item
        """
        try:
            episode: Episode = subitem.get(
                episode=animapping.tvdb_epoffset
                + (anilist_media.episodes or sys.maxsize)
            )
        except (plexapi.exceptions.NotFound, IndexError):
            return None

        history = self.plex_client.get_first_history(episode)
        if not history and not episode.lastViewedAt:
            return None
        if not history:
            return FuzzyDate.from_date(episode.lastViewedAt)

        return min(
            FuzzyDate.from_date(history.viewedAt) or 0,
            FuzzyDate.from_date(episode.lastViewedAt) or 0,
        )

    def __filter_mapped_episodes(
        self, subitem: Season, anilist_media: Media, animapping: AniMap
    ) -> list[Episode]:
        return self.plex_client.get_episodes(
            subitem,
            start=animapping.tvdb_epoffset + 1,
            end=animapping.tvdb_epoffset + (anilist_media.episodes or sys.maxsize),
        )

    def __filter_watched_episodes(
        self, subitem: Season, anilist_media: Media, animapping: AniMap
    ) -> list[Episode]:
        return self.plex_client.get_watched_episodes(
            subitem,
            start=animapping.tvdb_epoffset + 1,
            end=animapping.tvdb_epoffset + (anilist_media.episodes or sys.maxsize),
        )
