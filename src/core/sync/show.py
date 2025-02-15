import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Iterator

from plexapi.video import Episode, Season, Show

from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class ShowSyncClient(BaseSyncClient[Show, Season, list[Episode]]):
    def map_media(
        self, item: Show, **_
    ) -> Iterator[tuple[Season, list[Episode], AniMap | None, Media | None]]:
        """Maps a Plex item to potential AniList matches.

        Args:
            item (Show): Plex media item to map

        Returns:
            Iterator[tuple[Season, list[Episode], AniMap | None, Media | None]]: Mapping matches (child, grandchild, animapping, anilist_media)
        """
        guids = ParsedGuids.from_guids(item.guids)
        seasons: dict[int, Season] = {
            s.index: s
            for s in item.seasons(index__ge=0)
            if s.leafCount and (self.destructive_sync or s.viewedLeafCount)
        }
        unyielded_seasons = set(seasons.keys())

        for animapping in self.animap_client.get_mappings(
            **dict(guids), is_movie=False
        ):
            if not animapping.anilist_id:
                continue

            tvdb_mappings = animapping.parse_tvdb_mappings()

            filtered_seasons = {
                index: seasons.get(index)
                for index in {m.season for m in tvdb_mappings}
                if index in seasons
            }
            if not filtered_seasons:
                continue

            episodes: list[Episode] = []

            anilist_media = self.anilist_client.get_anime(animapping.anilist_id)
            if not anilist_media:
                continue

            for tvdb_mapping in tvdb_mappings:
                season = filtered_seasons.get(tvdb_mapping.season)
                if not season:
                    continue

                if tvdb_mapping.end:
                    episodes.extend(
                        e
                        for e in season.episodes()
                        if tvdb_mapping.start <= e.index <= tvdb_mapping.end
                    )
                else:
                    episodes.extend(
                        e for e in season.episodes() if e.index >= tvdb_mapping.start
                    )

                if tvdb_mapping.ratio > 0:
                    target_length = (
                        anilist_media.episodes or sys.maxsize // tvdb_mapping.ratio
                    )
                    episodes = [
                        e
                        for e in episodes[:target_length]
                        for _ in range(tvdb_mapping.ratio)
                    ]
                elif tvdb_mapping.ratio < 0:
                    target_length = (
                        anilist_media.episodes or sys.maxsize
                    ) * -tvdb_mapping.ratio
                    episodes = episodes[:target_length][:: -tvdb_mapping.ratio]

            if not episodes:
                continue

            all_seasons = Counter(e.parentIndex for e in episodes)
            primary_season = filtered_seasons[all_seasons.most_common(1)[0][0]]
            unyielded_seasons -= set(all_seasons.keys())

            yield primary_season, episodes, animapping, anilist_media

        for index in unyielded_seasons:
            if index < 1:
                continue
            season = seasons[index]
            yield season, season.episodes(), None, None

    def search_media(self, item: Show, child_item: Season) -> Media | None:
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
        self, item: Show, grandchild_items: list[Episode], anilist_media: Media, **_
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
            item if animapping.tvdb_season == -1 else subitem,
            index__gt=(animapping.tvdb_epoffset or 0),
            index__lte=(animapping.tvdb_epoffset or 0)
            + (anilist_media.episodes or sys.maxsize),
        )

        # We've watched all episodes and are in the process of watching them again
        if is_viewed and is_on_continue_watching:
            return MediaListStatus.REPEATING
        # We've watched all episodes
        if is_viewed:
            return MediaListStatus.COMPLETED
        # We've watched some episodes recently and have more remaining
        if is_on_continue_watching:
            return MediaListStatus.CURRENT

        is_parent_on_continue_watching = self.plex_client.is_on_continue_watching(item)
        is_in_deck_window = any(
            e.lastViewedAt.replace(tzinfo=timezone.utc)
            + self.plex_client.on_deck_window
            > datetime.now(timezone.utc)
            for e in watched_episodes
        )

        # We've watched some episodes recently but the last watched episode is from a different season
        if is_in_deck_window and is_parent_on_continue_watching:
            return MediaListStatus.CURRENT

        all_episodes = self.__filter_mapped_episodes(
            item=item,
            subitem=subitem,
            anilist_media=anilist_media,
            animapping=animapping,
        )
        is_all_available = len(all_episodes) >= (anilist_media.episodes or sys.maxsize)

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

    def _calculate_score(self, item: Show, child_item: Season, **_) -> int | None:
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

    def _calculate_repeats(self, grandchild_items: list[Episode], **_) -> int | None:
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
        self, grandchild_items: list[Episode], **_
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Args:
            subitem (Season): Specific item to sync
            animapping (AniMap): ID mapping information

        Returns:
            FuzzyDate | None: Start date for the media item
        """
        try:
            episode: Episode = subitem.get(episode=(animapping.tvdb_epoffset or 0) + 1)
        except (plexapi.exceptions.NotFound, IndexError):
            return None

        history: EpisodeHistory = self.plex_client.get_first_history(episode)

        last_viewed = (
            FuzzyDate.from_date(
                episode.lastViewedAt.replace(tzinfo=timezone.utc).astimezone(
                    self.anilist_client.user_tz
                )
            )
            if episode.lastViewedAt
            else None
        )
        history_viewed = (
            FuzzyDate.from_date(
                history.viewedAt.replace(tzinfo=timezone.utc).astimezone(
                    self.anilist_client.user_tz
                )
            )
            if history and history.viewedAt
            else None
        )

        if last_viewed and history_viewed:
            return min(last_viewed, history_viewed)
        return last_viewed or history_viewed

    def _calculate_completed_at(
        self, grandchild_items: list[Episode], **_
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
                    episode=(animapping.tvdb_epoffset or 0)
                    + (anilist_media.episodes or sys.maxsize)
                )
            except (plexapi.exceptions.NotFound, IndexError):
                return None

        history = self.plex_client.get_first_history(episode)

        last_viewed = (
            FuzzyDate.from_date(
                episode.lastViewedAt.replace(tzinfo=timezone.utc).astimezone(
                    self.anilist_client.user_tz
                )
            )
            if episode.lastViewedAt
            else None
        )
        history_viewed = (
            FuzzyDate.from_date(
                history.viewedAt.replace(tzinfo=timezone.utc).astimezone(
                    self.anilist_client.user_tz
                )
            )
            if history and history.viewedAt
            else None
        )

        if last_viewed and history_viewed:
            return min(last_viewed, history_viewed)
        return last_viewed or history_viewed

    def _filter_watched_episodes(self, episodes: list[Episode]) -> list[Episode]:
        """Filters watched episodes based on AniList entry.

        Args:
            episodes (list[Episode]): Episodes to filter

        Returns:
            list[Episode]: Filtered episodes
        """
        return [e for e in episodes if e.viewCount]
