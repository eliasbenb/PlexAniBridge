from datetime import timezone
from typing import Iterator

from plexapi.video import Movie, MovieHistory

from src import log
from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap

from .base import BaseSyncClient, ParsedGuids


class MovieSyncClient(BaseSyncClient[Movie, Movie, list[Movie]]):
    def map_media(
        self, item: Movie, **_
    ) -> Iterator[tuple[Movie, list[Movie], AniMap, Media]]:
        """Maps a Plex item to potential AniList matches.

        Args:
            item (Movie): Plex media item to map

        Returns:
            Iterator[tuple[Movie, list[Movie], AniMap, Media]]: Mapping matches (child, grandchild, animapping, anilist_media)
        """
        self.sync_stats.possible.add(str(item))

        guids = ParsedGuids.from_guids(item.guids)

        animapping: AniMap = next(
            iter(self.animap_client.get_mappings(**dict(guids), is_movie=True)),
            None,
        ) or AniMap(
            imdb_id=guids.imdb,
            tmdb_movie_id=guids.tmdb,
            tvdb_id=guids.tvdb,
        )

        try:
            if animapping.anilist_id:
                anilist_media = self.anilist_client.get_anime(animapping.anilist_id)
            else:
                anilist_media = self.search_media(item)
        except Exception:
            log.error(
                f"Failed to fetch AniList data for {self._debug_log_title(item)}: "
                f"{self._debug_log_ids(item.ratingKey, item.guid, guids, animapping.anilist_id)}",
                exc_info=True,
            )
            self.sync_stats.failed += 1
            return

        if not anilist_media:
            log.debug(
                f"No AniList entry could be found for {self._debug_log_title(item)} "
                f"{self._debug_log_ids(item.ratingKey, item.guid, guids)}"
            )
            self.sync_stats.not_found += 1
            return

        yield item, [item], animapping, anilist_media

    def search_media(self, item: Movie, **_) -> Media | None:
        """Searches for matching AniList entry by title.

        For movies, we search for single episode entries.

        Args:
            item (Movie): Main Plex item

        Returns:
            Media | None: Matching AniList entry or None if not found
        """
        if self.fuzzy_search_threshold == -1:
            return None

        results = self.anilist_client.search_anime(item.title, True, 1)
        return self._best_search_result(item.title, results)

    def _calculate_status(self, item: Movie, **_) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Args:
            item (Movie): Main Plex media item

        Returns:
            MediaListStatus | None: Watch status for the media item
        """
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

    def _calculate_score(self, item: Movie, **_) -> int | None:
        """Calculates the user rating for a media item.

        Args:
            item (Movie): Main Plex media item

        Returns:
            int | None: User rating for the media item
        """
        score = item.userRating
        return self._normalize_score(score) if score else None

    def _calculate_progress(self, item: Movie, anilist_media: Media, **_) -> int | None:
        """Calculates the progress for a media item.

        Args:
            item (Movie): Main Plex media item
            anilist_media (Media): AniList media item

        Returns:
            int | None: Progress for the media item
        """
        return (anilist_media.episodes or 1) if item.viewCount else None

    def _calculate_repeats(self, item: Movie, **_) -> int | None:
        """Calculates the number of repeats for a media item.

        Args:
            item (Movie): Main Plex media item

        Returns:
            int | None: Number of repeats for the media item
        """
        return item.viewCount - 1 if item.viewCount else None

    def _calculate_started_at(self, item: Movie, **_) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Args:
            item (Movie): Main Plex media item

        Returns:
            FuzzyDate | None: Start date for the media item
        """
        history: MovieHistory = self.plex_client.get_first_history(item)

        last_viewed = (
            FuzzyDate.from_date(
                item.lastViewedAt.replace(tzinfo=timezone.utc).astimezone(
                    self.anilist_client.user_tz
                )
            )
            if item.lastViewedAt
            else None
        )
        history_viewed = (
            FuzzyDate.from_date(
                history.viewedAt.replace(tzinfo=timezone.utc).astimezone(
                    self.anilist_client.user_tz
                )
            )
            if history
            else None
        )

        if last_viewed and history_viewed:
            return min(last_viewed, history_viewed)
        return last_viewed or history_viewed

    def _calculate_completed_at(self, item: Movie, **_) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Args:
            item (Movie): Main Plex media item

        Returns:
            FuzzyDate | None: Completion date for the media item
        """
        return self._calculate_started_at(item, **_)

    def _calculate_notes(
        self,
        item: Movie,
        **_,
    ) -> str | None:
        """Chooses the most relevant user notes for a media item.

        Args:
            item (Movie): Plex media item

        Returns:
            str | None: User notes for the media item
        """
        return self.plex_client.get_user_review(item)

    def _debug_log_title(self, item: Movie, **_) -> str:
        """Creates a debug-friendly string of media titles.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args
            item (T): Plex media item

        Returns:
            str: Debug-friendly string of media titles
        """
        return f"$$'{item.title}'$$"

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
