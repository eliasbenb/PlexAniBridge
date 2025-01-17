import sys
from datetime import datetime
from functools import lru_cache
from typing import Iterator

import plexapi.exceptions
from plexapi.video import Episode, Season, Show

from src.models.anilist import FuzzyDate, Media, MediaListStatus
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
            elif animapping.tvdb_season in season_map:
                try:
                    unyielded_seasons.remove(animapping.tvdb_season)
                except KeyError:
                    pass
                yield season_map[animapping.tvdb_season], animapping, guids
            elif animapping.tvdb_season == -1 and 1 in unyielded_seasons:
                unyielded_seasons = set()
                yield season_map[1], animapping, guids

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
            item=item,
            subitem=subitem,
            anilist_media=anilist_media,
            animapping=animapping,
        )
        is_viewed = len(watched_episodes) >= (anilist_media.episodes or sys.maxsize)
        is_partially_viewed = len(watched_episodes) > 0
        is_on_continue_watching = self.plex_client.is_on_continue_watching(
            subitem,
            index__gt=animapping.tvdb_epoffset,
            index__lte=animapping.tvdb_epoffset
            + (anilist_media.episodes or sys.maxsize),
        )

        # We've watched all episodes and are in the process of watching them again
        if is_viewed and is_on_continue_watching:
            return MediaListStatus.REPEATING
        # We've watched all episodes
        if is_viewed:
            return MediaListStatus.COMPLETED
        # We've watched some episode recently and have more remaining
        if is_on_continue_watching:
            return MediaListStatus.CURRENT

        all_episodes = self.__filter_mapped_episodes(
            item=item,
            subitem=subitem,
            anilist_media=anilist_media,
            animapping=animapping,
        )
        is_all_available = len(all_episodes) >= (anilist_media.episodes or sys.maxsize)
        is_in_deck_window = any(
            e.lastViewedAt + self.plex_client.on_deck_window > datetime.now()
            for e in watched_episodes
        )

        # We've watched some episodes recently and the Plex server doesn't have all episodes
        if is_in_deck_window and not is_all_available:
            return MediaListStatus.CURRENT

        is_on_watchlist = self.plex_client.is_on_watchlist(item)

        # We've watched some episodes but it's no longer on continue watching. However, it's on the watchlist
        if is_partially_viewed and is_on_watchlist:
            return MediaListStatus.PAUSED
        # We haven't watched any episodes and it's on the watchlist
        if is_on_watchlist:
            return MediaListStatus.PLANNING
        # We've watched some episodes but it's not on continue watching or the watchlist
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
        score = subitem.userRating or item.userRating
        return self._normalize_score(score) if score else None

    def _calculate_progress(
        self, item: Show, subitem: Season, anilist_media: Media, animapping: AniMap
    ) -> int | None:
        """Calculates the progress for a media item.

        Args:
            item (Show): Main Plex media item
            subitem (Season): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            int | None: Progress for the media item
        """
        return (
            len(
                self.__filter_watched_episodes(
                    item=item,
                    subitem=subitem,
                    anilist_media=anilist_media,
                    animapping=animapping,
                )
            )
            or None
        )

    def _calculate_repeats(
        self,
        item: Show,
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
        episodes = self.__filter_mapped_episodes(
            item=item,
            subitem=subitem,
            anilist_media=anilist_media,
            animapping=animapping,
        )
        least_views = min((e.viewCount for e in episodes), default=0)
        return least_views - 1 if least_views else None

    def _calculate_started_at(
        self, subitem: Season, animapping: AniMap, **_
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Args:
            subitem (Season): Specific item to sync
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
        if not episode.lastViewedAt:
            return FuzzyDate.from_date(history.viewedAt)

        return min(
            FuzzyDate.from_date(history.viewedAt),
            FuzzyDate.from_date(episode.lastViewedAt),
        )

    def _calculate_completed_at(
        self, item: Show, subitem: Season, anilist_media: Media, animapping: AniMap
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Args:
            item (Show): Main Plex media item
            subitem (Season): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            FuzzyDate | None: Completion date for the media item
        """
        if animapping.tvdb_season == -1:
            episodes = self.__filter_mapped_episodes(
                item=item,
                subitem=subitem,
                anilist_media=anilist_media,
                animapping=animapping,
            )
            if len(episodes) < (anilist_media.episodes or sys.maxsize):
                return None
            try:
                episode = episodes[anilist_media.episodes - 1]
            except IndexError:
                return None
        else:
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
        if not episode.lastViewedAt:
            return FuzzyDate.from_date(history.viewedAt)

        return min(
            FuzzyDate.from_date(history.viewedAt),
            FuzzyDate.from_date(episode.lastViewedAt),
        )

    @lru_cache
    def __filter_mapped_episodes(
        self, item: Show, subitem: Season, anilist_media: Media, animapping: AniMap
    ) -> list[Episode]:
        """Filter episodes based on the mapped AniList entry.

        Only episodes in the mapped range are returned.

        Args:
            item (Show): Main Plex media item
            subitem (Season): Specific item to sync
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            list[Episode]: Filtered episodes
        """
        if animapping.tvdb_season == -1:
            episodes: list[Episode] = []
            seasons: list[Season] = item.seasons(index__gt=0)
            episodes_count = 0

            for season in seasons:
                tmp_episodes: list[Episode] = season.episodes()
                max_episode_index = tmp_episodes[-1].index if tmp_episodes else 0

                if episodes_count + max_episode_index >= anilist_media.episodes:
                    episodes.extend(
                        (
                            e
                            for e in tmp_episodes
                            if e.index <= anilist_media.episodes - episodes_count
                        )
                    )
                    break

                episodes.extend(tmp_episodes)
                episodes_count += max_episode_index
            return episodes

        return self.plex_client.get_episodes(
            subitem,
            start=animapping.tvdb_epoffset + 1,
            end=animapping.tvdb_epoffset + (anilist_media.episodes or sys.maxsize),
        )

    def __filter_watched_episodes(
        self, item: Show, subitem: Season, anilist_media: Media, animapping: AniMap
    ) -> list[Episode]:
        """Filter episodes based on the mapped AniList entry and watched status.

        Only episodes in the mapped range that have been watched are returned.

        Args:
            item (Show): Main Plex media item
            subitem (Season): The Plex season to filter
            anilist_media (Media): Matched AniList entry
            animapping (AniMap): ID mapping information

        Returns:
            list[Episode]: Filtered episodes
        """
        return [
            e
            for e in self.__filter_mapped_episodes(
                item=item,
                subitem=subitem,
                anilist_media=anilist_media,
                animapping=animapping,
            )
            if e.viewCount
        ]
