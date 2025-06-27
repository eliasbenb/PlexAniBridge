from typing import AsyncIterator

from tzlocal import get_localzone

from plexapi.video import Movie
from src import log
from src.core.sync.base import BaseSyncClient, ParsedGuids
from src.models.anilist import FuzzyDate, Media, MediaListStatus
from src.models.animap import AniMap


class MovieSyncClient(BaseSyncClient[Movie, Movie, list[Movie]]):
    async def map_media(
        self, item: Movie
    ) -> AsyncIterator[tuple[Movie, list[Movie], AniMap, Media]]:
        """Maps a Plex item to potential AniList matches.

        Args:
            item (Movie): Plex media item to map

        Returns:
            AsyncIterator[tuple[Movie, list[Movie], AniMap, Media]]: Mapping matches (child, grandchild, animapping, anilist_media)
        """
        self.sync_stats.possible.add(str(item))

        guids = ParsedGuids.from_guids(item.guids)

        animapping: AniMap = next(
            iter(
                self.animap_client.get_mappings(
                    imdb=guids.imdb, tmdb=guids.tmdb, tvdb=guids.tvdb, is_movie=True
                )
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

    async def search_media(self, item: Movie, child_item: Movie) -> Media | None:
        """Searches for matching AniList entry by title.

        For movies, we search for single episode entries.

        Args:
            item (Movie): Main Plex item

        Returns:
            Media | None: Matching AniList entry or None if not found
        """
        if self.search_fallback_threshold == -1:
            return None

        results = await self.anilist_client.search_anime(item.title, True, 1)
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
            item (Movie): Main Plex media item
            child_item (Movie): Child Plex media item (same as item for movies)
            grandchild_items (list[Movie]): List containing the movie item
            anilist_media (Media): AniList media entry
            animapping (AniMap): Mapping between Plex and AniList

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
            item (Movie): Main Plex media item
            child_item (Movie): Child Plex media item (same as item for movies)
            grandchild_items (list[Movie]): List containing the movie item
            anilist_media (Media): AniList media entry
            animapping (AniMap): Mapping between Plex and AniList

        Returns:
            int | float | None: User rating for the media item (normalized to AniList scale)
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
            item (Movie): Main Plex media item
            child_item (Movie): Child Plex media item (same as item for movies)
            grandchild_items: list[Movie]: List containing the movie item
            anilist_media (Media): AniList media entry
            animapping (AniMap): Mapping between Plex and AniList

        Returns:
            int | None: Progress for the media item (total episodes if watched, None if not)
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
            item (Movie): Main Plex media item
            child_item (Movie): Child Plex media item (same as item for movies)
            grandchild_items: list[Movie]: List containing the movie item
            anilist_media (Media): AniList media entry
            animapping (AniMap): Mapping between Plex and AniList

        Returns:
            int | None: Number of repeats for the media item (viewCount - 1)
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
            item (Movie): Main Plex media item
            child_item (Movie): Child Plex media item (same as item for movies)
            grandchild_items: list[Movie]: List containing the movie item
            anilist_media (Media): AniList media entry
            animapping (AniMap): Mapping between Plex and AniList

        Returns:
            FuzzyDate | None: Start date for the media item (earliest view date)
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
            item (Movie): Main Plex media item
            child_item (Movie): Child Plex media item (same as item for movies)
            grandchild_items: list[Movie]: List containing the movie item
            anilist_media (Media): AniList media entry
            animapping (AniMap): Mapping between Plex and AniList

        Returns:
            FuzzyDate | None: Completion date for the media item (same as start date for movies)
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
            item (Movie): Main Plex media item
            child_item (Movie): Child Plex media item (same as item for movies)
            grandchild_items: list[Movie]: List containing the movie item
            anilist_media (Media): AniList media entry
            animapping (AniMap): Mapping between Plex and AniList

        Returns:
            str | None: User notes for the media item (from Plex user review)
        """
        return await self.plex_client.get_user_review(item)

    def _debug_log_title(self, item: Movie, animapping: AniMap | None = None) -> str:
        """Creates a debug-friendly string of media titles.

        The outputted string uses color formatting syntax with the `$$` delimiters.

        Args:
            item (Movie): Plex media item
            animapping (AniMap | None): Optional mapping data (not used for movies)

        Returns:
            str: Debug-friendly string of media titles
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
            key (int): Plex rating key
            plex_id (str): Plex ID
            guids (ParsedGuids): Plex GUIDs
            anilist_id (int | None): AniList ID

        Returns:
            str: Debug-friendly string of media identifiers
        """
        return f"$${{key: {key}, plex_id: {plex_id}, {guids}{f', anilist_id: {anilist_id}' if anilist_id else ''}}}$$"
