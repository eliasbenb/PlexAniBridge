"""Sync client for Plex movies to AniList."""

from collections.abc import AsyncIterator

from tzlocal import get_localzone

from plexapi.video import Movie
from src import log
from src.core.sync.base import BaseSyncClient, ParsedGuids
from src.core.sync.stats import ItemIdentifier
from src.models.db.animap import AniMap
from src.models.schemas.anilist import FuzzyDate, Media, MediaListStatus


class MovieSyncClient(BaseSyncClient[Movie, Movie, list[Movie]]):
    """Sync client for Plex movies to AniList.

    This client handles:
        - Mapping Plex movies to AniList entries using GUIDs (IMDB, TMDB, etc.).
        - Searching for AniList entries by title if no GUID mapping is found.
        - Determining watch status, ratings, progress, repeats, start/completion dates.
    """

    async def map_media(
        self, item: Movie
    ) -> AsyncIterator[tuple[Movie, list[Movie], AniMap, Media]]:
        """Maps a Plex movie to potential AniList matches.

        Searches for AniList entries that match the provided Plex movie using
        GUID mappings (IMDB, TMDB) and falls back to title-based search if
        no mapping is found.

        Args:
            item (Movie): Plex movie to map.

        Yields:
            tuple[Movie, list[Movie], AniMap, Media]: A tuple containing:
                - Movie: The movie itself.
                - list[Movie]: List containing the movie.
                - AniMap: AniMap entry with ID mappings.
                - Media: Matched AniList media entry.
        """
        guids = ParsedGuids.from_guids(item.guids)

        animapping: AniMap = next(
            self.animap_client.get_mappings(
                imdb=guids.imdb, tmdb=guids.tmdb, tvdb=guids.tvdb, is_movie=True
            ),
            AniMap(
                anidb_id=None,
                anilist_id=0,
                imdb_id=[guids.imdb] if guids.imdb else None,
                mal_id=None,
                tmdb_movie_id=[guids.tmdb] if guids.tmdb else None,
                tmdb_show_id=None,
                tvdb_id=guids.tvdb,
                tvdb_mappings=None,
            ),
        )

        try:
            if animapping.anilist_id:
                anilist_media = await self.anilist_client.get_anime(
                    animapping.anilist_id
                )
            else:
                _anilist_media = await self.search_media(item, item)
                if not _anilist_media:
                    return
                anilist_media = _anilist_media
        except Exception:
            log.error(
                f"Failed to fetch AniList data for {self._debug_log_title(item)}: "
                f"{
                    self._debug_log_ids(
                        item.ratingKey, item.guid, guids, animapping.anilist_id
                    )
                }",
                exc_info=True,
            )
            return

        if not anilist_media:
            log.warning(
                f"No AniList entry could be found for {self._debug_log_title(item)} "
                f"{self._debug_log_ids(item.ratingKey, item.guid, guids)}"
            )
            return

        yield item, [item], animapping, anilist_media

    async def search_media(self, item: Movie, child_item: Movie) -> Media | None:
        """Searches for matching AniList entry by title.

        For movies, searches for single-episode entries.

        Args:
            item (Movie): Main Plex item.
            child_item (Movie): Child Plex item.

        Returns:
            Media | None: Matching AniList entry or None if not found.
        """
        if self.search_fallback_threshold == -1:
            return None

        results = [
            result
            async for result in self.anilist_client.search_anime(
                search_str=item.title, is_movie=True, episodes=1
            )
        ]
        return self._best_search_result(item.title, results)

    async def _calculate_status(
        self,
        item: Movie,
        child_item: Movie,
        grandchild_items: list[Movie],
        anilist_media: Media,
        animapping: AniMap,
    ) -> MediaListStatus | None:
        """Calculates the watch status for a media item.

        Args:
            item (Movie): Main Plex media item.
            child_item (Movie): Child Plex media item (same as item for movies).
            grandchild_items (list[Movie]): List containing the movie item.
            anilist_media (Media): AniList media entry.
            animapping (AniMap): Mapping between Plex and AniList.

        Returns:
            MediaListStatus | None: Watch status for the media item.
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

        # We've watched part of it and it's not on continue watching. However, we've
        # watchlisted it
        if is_on_watchlist and is_partially_viewed:
            return MediaListStatus.PAUSED
        # It's on our watchlist and we haven't watched it yet
        if is_on_watchlist:
            return MediaListStatus.PLANNING
        # We've watched it, but we don't want to continue watching it
        if is_partially_viewed:
            return MediaListStatus.DROPPED
        return None

    async def _get_all_trackable_items(self, item: Movie) -> list[ItemIdentifier]:
        """Get all trackable items for a movie.

        For movies, this returns the movie itself as it is a single-episode item.

        Args:
            item (Movie): Plex movie item.

        Returns:
            list[ItemIdentifier]: List of all trackable items (the movie itself).
        """
        return [ItemIdentifier.from_item(item)]

    async def _calculate_score(
        self,
        item: Movie,
        child_item: Movie,
        grandchild_items: list[Movie],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | float | None:
        """Calculates the user rating for a media item.

        Args:
            item (Movie): Main Plex media item.
            child_item (Movie): Child Plex media item (same as item for movies).
            grandchild_items (list[Movie]): List containing the movie item.
            anilist_media (Media): AniList media entry.
            animapping (AniMap): Mapping between Plex and AniList.

        Returns:
            int | float | None: User rating for the media item (normalized by scale).
        """
        score = item.userRating
        return self._normalize_score(score) if score else None

    async def _calculate_progress(
        self,
        item: Movie,
        child_item: Movie,
        grandchild_items: list[Movie],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the progress for a media item.

        Args:
            item (Movie): Main Plex media item.
            child_item (Movie): Child Plex media item (same as item for movies).
            grandchild_items (list[Movie]): List containing the movie item.
            anilist_media (Media): AniList media entry.
            animapping (AniMap): Mapping between Plex and AniList.

        Returns:
            int | None: Progress for the media item (None if not watched).
        """
        return (anilist_media.episodes or 1) if item.viewCount else None

    async def _calculate_repeats(
        self,
        item: Movie,
        child_item: Movie,
        grandchild_items: list[Movie],
        anilist_media: Media,
        animapping: AniMap,
    ) -> int | None:
        """Calculates the number of repeats for a media item.

        Args:
            item (Movie): Main Plex media item.
            child_item (Movie): Child Plex media item (same as item for movies).
            grandchild_items (list[Movie]): List containing the movie item.
            anilist_media (Media): AniList media entry.
            animapping (AniMap): Mapping between Plex and AniList.

        Returns:
            int | None: Number of repeats for the media item (viewCount - 1).
        """
        return item.viewCount - 1 if item.viewCount else None

    async def _calculate_started_at(
        self,
        item: Movie,
        child_item: Movie,
        grandchild_items: list[Movie],
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the start date for a media item.

        Args:
            item (Movie): Main Plex media item.
            child_item (Movie): Child Plex media item (same as item for movies).
            grandchild_items (list[Movie]): List containing the movie item.
            anilist_media (Media): AniList media entry.
            animapping (AniMap): Mapping between Plex and AniList.

        Returns:
            FuzzyDate | None: Start date for the media item (earliest view date).
        """
        history = await self.plex_client.get_history(item)
        first_history = min(history, key=lambda h: h.viewedAt) if history else None

        last_viewed = FuzzyDate.from_date(
            item.lastViewedAt.replace(tzinfo=get_localzone()).astimezone(
                self.anilist_client.user_tz
            )
            if item.lastViewedAt
            else None
        )
        history_viewed = FuzzyDate.from_date(
            first_history.viewedAt.replace(tzinfo=get_localzone()).astimezone(
                self.anilist_client.user_tz
            )
            if first_history and first_history.viewedAt
            else None
        )

        if last_viewed and history_viewed:
            return min(last_viewed, history_viewed)
        return last_viewed or history_viewed

    async def _calculate_completed_at(
        self,
        item: Movie,
        child_item: Movie,
        grandchild_items: list[Movie],
        anilist_media: Media,
        animapping: AniMap,
    ) -> FuzzyDate | None:
        """Calculates the completion date for a media item.

        Args:
            item (Movie): Main Plex media item.
            child_item (Movie): Child Plex media item (same as item for movies).
            grandchild_items (list[Movie]): List containing the movie item.
            anilist_media (Media): AniList media entry.
            animapping (AniMap): Mapping between Plex and AniList.

        Returns:
            FuzzyDate | None: Completion date for the media item (same as start date
                              for movies).
        """
        return await self._calculate_started_at(
            item, child_item, grandchild_items, anilist_media, animapping
        )

    async def _calculate_notes(
        self,
        item: Movie,
        child_item: Movie,
        grandchild_items: list[Movie],
        anilist_media: Media,
        animapping: AniMap,
    ) -> str | None:
        """Chooses the most relevant user notes for a media item.

        Args:
            item (Movie): Main Plex media item.
            child_item (Movie): Child Plex media item (same as item for movies).
            grandchild_items (list[Movie]): List containing the movie item.
            anilist_media (Media): AniList media entry.
            animapping (AniMap): Mapping between Plex and AniList.

        Returns:
            str | None: User notes for the media item (from Plex user review).
        """
        return await self.plex_client.get_user_review(item)

    def _debug_log_title(self, item: Movie, animapping: AniMap | None = None) -> str:
        """Creates a debug-friendly string of media titles.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            item (Movie): Plex media item.
            animapping (AniMap | None): Optional mapping data (not used for movies).

        Returns:
            str: Debug-friendly string of media titles.
        """
        return f"$$'{item.title}'$$"

    def _debug_log_ids(
        self,
        key: int | str,
        plex_id: str | None,
        guids: ParsedGuids,
        anilist_id: int | None = None,
    ) -> str:
        """Creates a debug-friendly string of media identifiers.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            key (int | str): Plex rating key.
            plex_id (str | None): Plex ID.
            guids (ParsedGuids): Plex GUIDs.
            anilist_id (int | None): AniList ID.

        Returns:
            str: Debug-friendly string of media identifiers.
        """
        return (
            f"$${{key: {key}, plex_id: {plex_id}, {guids}"
            f"{f', anilist_id: {anilist_id}' if anilist_id else ''}}}$$"
        )
