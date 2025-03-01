import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Iterator

from plexapi.video import Episode, Season, Show

from src import log
from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class ShowSyncClient(BaseSyncClient[Show, Season, list[Episode]]):
    def map_media(
        self, item: Show, **_
    ) -> Iterator[tuple[Season, list[Episode], AniMap, Media]]:
        """Maps a Plex item to potential AniList matches.

        Args:
            item (Show): Plex media item to map

        Returns:
            Iterator[tuple[Season, list[Episode], AniMap, Media]]: Mapping matches (child, grandchild, animapping, anilist_media)
        """
        guids = ParsedGuids.from_guids(item.guids)

        seasons: dict[int, Season] = {
            s.index: s
            for s in item.seasons()
            if s.leafCount and (self.full_scan or s.viewedLeafCount)
        }
        all_episodes: list[Episode] = [
            e for e in item.episodes() if e.parentIndex in seasons
        ]

        self.sync_stats.possible |= {str(e) for e in all_episodes}
        unyielded_seasons = set(seasons.keys())

        for animapping in self.animap_client.get_mappings(
            **dict(guids), is_movie=False
        ):
            if not animapping.anilist_id:
                continue

            filtered_seasons = {
                index: seasons.get(index)
                for index in {m.season for m in animapping.parsed_tvdb_mappings}
                if index in seasons
            }
            if not filtered_seasons:
                continue

            episodes: list[Episode] = []

            try:
                anilist_media = self.anilist_client.get_anime(animapping.anilist_id)
            except Exception:
                anilist_media = None
                self.sync_stats.failed += 1

            if not anilist_media:
                continue

            for tvdb_mapping in animapping.parsed_tvdb_mappings:
                season = filtered_seasons.get(tvdb_mapping.season)
                if not season:
                    continue

                if tvdb_mapping.end:
                    episodes.extend(
                        e
                        for e in all_episodes
                        if e.parentIndex == season.index
                        and tvdb_mapping.start <= e.index <= tvdb_mapping.end
                    )
                else:
                    episodes.extend(
                        e
                        for e in all_episodes
                        if e.parentIndex == season.index
                        if e.index >= tvdb_mapping.start
                    )

                if tvdb_mapping.ratio > 0:
                    episodes = [e for e in episodes for _ in range(tvdb_mapping.ratio)]
                elif tvdb_mapping.ratio < 0:
                    episodes = [
                        e
                        for i, e in enumerate(episodes, start=1)
                        if i % tvdb_mapping.ratio != 0
                    ]

            all_seasons = Counter(e.parentIndex for e in episodes)
            unyielded_seasons -= set(all_seasons.keys())

            if not episodes:
                continue

            primary_season = filtered_seasons[all_seasons.most_common(1)[0][0]]

            yield primary_season, episodes, animapping, anilist_media

        for index in unyielded_seasons:
            if index < 1:
                continue
            season = seasons[index]

            try:
                anilist_media = self.search_media(item, season)
            except Exception:
                anilist_media = None
                self.sync_stats.failed += 1
                log.error(
                    f"Failed to fetch AniList data for {self._debug_log_title(item)}: ",
                    exc_info=True,
                )

            if not anilist_media:
                self.sync_stats.not_found += 1
                continue

            episodes = [e for e in all_episodes if e.parentIndex == season.index]

            animapping = AniMap(
                anilist_id=anilist_media.id,
                imdb_id=guids.imdb,
                tmdb_show_id=guids.tmdb,
                tvdb_id=guids.tvdb,
                tvdb_mappings={f"s{index}": ""},
            )

            yield season, episodes, animapping, anilist_media

    def search_media(self, item: Show, child_item: Season) -> Media | None:
        """Searches for matching AniList entry by title.

        For shows, we search for entries with matching episode counts and
        similar titles (fuzzy search).

        Args:
            item (T): Grandparent Plex media item
            child_item (S): Target child item to sync

        Returns:
            Media | None: Matching AniList entry or None if not found
        """
        if self.fuzzy_search_threshold == -1:
            return None
        if child_item.parentIndex == 0:
            return None

        episodes = child_item.leafCount
        results = self.anilist_client.search_anime(
            item.title, is_movie=False, episodes=episodes
        )
        return self._best_search_result(item.title, results)

    def _calculate_status(
        self, item: Show, grandchild_items: list[Episode], anilist_media: Media, **_
    ) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Args:
            item (Show): Main Plex media item
            grandchild_items (list[Episode]): List of relevant episodes
            anilist_media (Media): Matched AniList entry

        Returns:
            MediaListStatus | None: Watch status for the media item
        """
        all_episodes = grandchild_items
        is_all_available = len(all_episodes) >= (anilist_media.episodes or sys.maxsize)

        watched_episodes = self._filter_watched_episodes(all_episodes)
        is_all_watched = len(watched_episodes) >= (
            anilist_media.episodes or sys.maxsize
        )
        is_partially_watched = len(watched_episodes) > 0

        continue_watching_episode = self.plex_client.get_continue_watching(item)
        is_parent_on_continue_watching = bool(continue_watching_episode)
        is_on_continue_watching = continue_watching_episode in all_episodes

        # We've watched all episodes and are in the process of watching them again
        if is_all_watched and is_on_continue_watching:
            return MediaListStatus.REPEATING
        # We've watched all episodes
        if is_all_watched:
            return MediaListStatus.COMPLETED
        # We've watched some episodes recently and have more remaining
        if is_on_continue_watching:
            return MediaListStatus.CURRENT

        is_in_deck_window = any(
            e.lastViewedAt.replace(tzinfo=timezone.utc)
            + self.plex_client.on_deck_window
            > datetime.now(timezone.utc)
            for e in watched_episodes
        )

        # We've watched some episodes recently but the last watched episode is from a different season
        if is_in_deck_window and is_parent_on_continue_watching:
            return MediaListStatus.CURRENT
        # We've watched some episodes recently and the Plex server doesn't have all episodes
        if is_in_deck_window and not is_all_available:
            return MediaListStatus.CURRENT

        is_on_watchlist = self.plex_client.is_on_watchlist(item)

        # We've watched some episodes but it's no longer on continue watching. However, it's on the watchlist
        if is_partially_watched and is_on_watchlist:
            return MediaListStatus.PAUSED
        # We haven't watched any episodes and it's on the watchlist
        if is_on_watchlist:
            return MediaListStatus.PLANNING
        # We've watched some episodes but it's not on continue watching or the watchlist
        if is_partially_watched:
            return MediaListStatus.DROPPED
        return None

    def _calculate_score(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        animapping: AniMap,
        **_,
    ) -> int | None:
        """Calculates the user rating for a media item.

        Args:
            item (Show): Main Plex media item
            child_item (Season): Specific item to sync
            grandchild_items (list[Episode]): List of relevant episodes
            animapping (AniMap): Matched AniMap entry

        Returns:
            int | None: User rating for the media item
        """
        if all(e.userRating for e in grandchild_items):
            score = sum(e.userRating for e in grandchild_items) / len(grandchild_items)
        elif animapping.length == len(grandchild_items) == 1:
            score = grandchild_items[0].userRating
        elif child_item.userRating:
            score = child_item.userRating
        elif item.userRating:
            score = item.userRating
        else:
            score = None

        return self._normalize_score(score)

    def _calculate_progress(
        self, grandchild_items: list[Episode], anilist_media: Media, **_
    ) -> int | None:
        """Calculates the progress for a media item.

        Args:
            grandchild_items (list[Episode]): List of relevant episodes
            anilist_media (Media): Matched AniList entry

        Returns:
            int | None: Progress for the media item
        """
        watched_episodes = len(self._filter_watched_episodes(grandchild_items))
        return min(watched_episodes, anilist_media.episodes or watched_episodes)

    def _calculate_repeats(self, grandchild_items: list[Episode], **_) -> int | None:
        """Calculates the number of repeats for a media item.

        Args:
            grandchild_items (list[Episode]): List of relevant episodes

        Returns:
            int | None: Number of repeats for the media item
        """
        least_views = min(
            (e.viewCount for e in self._filter_watched_episodes(grandchild_items)),
            default=0,
        )
        return least_views - 1 if least_views else None

    def _calculate_started_at(
        self, grandchild_items: list[Episode], **_
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Args:
            grandchild_items (list[Episode]): List of relevant episodes

        Returns:
            FuzzyDate | None: Start date for the media item
        """
        return self._get_last_watched_date(grandchild_items[0])

    def _calculate_completed_at(
        self, grandchild_items: list[Episode], **_
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Args:
            grandchild_items (list[Episode]): List of relevant episodes

        Returns:
            FuzzyDate | None: Completion date for the media item
        """
        return self._get_last_watched_date(grandchild_items[-1])

    def _calculate_notes(
        self,
        item: Show,
        child_item: Season,
        grandchild_items: list[Episode],
        anilist_media: Media,
        **_,
    ) -> str | None:
        """Chooses the most relevant user notes for a media item.

        Must be implemented by subclasses to handle different media types.

        Args:
            item (Show): Grandparent Plex media item
            child_item (Season): Parent Plex media item
            grandchild_items (list[Episode]): List of relevant episodes
            anilist_media (Media): Matched AniList entry

        Returns:
            str | None: User notes for the media item
        """
        if len(grandchild_items) == anilist_media.episodes == 1:
            return self.plex_client.get_user_review(grandchild_items[0])
        return self.plex_client.get_user_review(
            child_item
        ) or self.plex_client.get_user_review(item)

    def _debug_log_title(
        self,
        item: Show,
        animapping: AniMap | None = None,
    ) -> str:
        """Creates a debug-friendly string of media titles.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            item (Show): Grandparent Plex media item
            animapping (AniMap | None): AniMap entry for the media

        Returns:
            str: Debug-friendly string of media titles
        """
        mappings_str = (
            ", ".join(str(m) for m in animapping.parsed_tvdb_mappings)
            if animapping
            else ""
        )
        return (
            f"$$'{item.title} ({mappings_str})'$$"
            if mappings_str
            else f"$$'{item.title}'$$"
        )

    def _debug_log_ids(
        self,
        key: int,
        plex_id: str,
        guids: ParsedGuids,
        anilist_id: int | None = None,
    ) -> str:
        """Creates a debug-friendly string of media identifiers.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            key (int): Plex rating key
            plex_id (str): Plex ID
            guids (ParsedGuids): Plex GUIDs
            anilist_id (int | None): AniList ID

        Returns:
            str: Debug-friendly string of media identifiers
        """
        return f"$${{key: {key}, plex_id: {plex_id}, {guids}{f', anilist_id: {anilist_id}' if anilist_id else ''}}}$$"

    def _get_last_watched_date(self, episode: Episode) -> FuzzyDate | None:
        """Gets the last watched date for an episode.

        Args:
            episode (Episode): Episode to check

        Returns:
            FuzzyDate | None: Last watched date for the episode
        """
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
