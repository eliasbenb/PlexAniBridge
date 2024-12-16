from datetime import datetime, timedelta
from typing import Any, Optional

import plexapi.exceptions
from plexapi.library import ShowSection
from plexapi.video import Episode, Season, Show

from src import log
from src.models.anilist import AniListMedia, AniListMediaListStatus
from src.models.animap import AniMap

from .base import BaseSyncClient


class ShowSyncClient(BaseSyncClient[Show, ShowSection]):
    def _get_media_to_sync(
        self, section: ShowSection, last_synced: Optional[datetime]
    ) -> list[Show]:
        if last_synced:
            return section.search(
                filters={
                    "or": [
                        {"updatedAt>>=": last_synced},
                        {"lastViewedAt>>=": last_synced},
                        {"lastRatedAt>>=": last_synced},
                    ]
                }
            )
        return section.all()

    def _process_media_item(self, show: Show) -> None:
        title: str = show.title
        guids = self._format_guids(show.guids, is_movie=False)

        animappings = self.animap_client.get_mappings(**guids)

        if not animappings:
            log.debug(
                f"{self.__class__.__name__}: No mappings found for show '{title}'"
            )
            return

        log.debug(
            f"{self.__class__.__name__}: Found {len(animappings)} mappings for show '{title}' "
            f"{{anidb_id: {[am.anidb_id for am in animappings]}}}"
        )

        for animapping in animappings:
            self._process_show_mapping(show, animapping)

    def _process_show_mapping(self, show: Show, animapping: AniMap) -> None:
        if not animapping.tvdb_season:
            return

        try:
            season = self._get_season(show, animapping.tvdb_season)
            if season:
                show_review = self.plex_client.get_user_review(show)
                self._process_season(show, season, show_review, animapping)
        except plexapi.exceptions.NotFound:
            log.debug(
                f"{self.__class__.__name__}: Season {animapping.tvdb_season} not found for show '{show.title}'"
            )

    def _get_season(self, show: Show, season_number: int) -> Optional[Season]:
        try:
            return show.season(season=season_number)
        except plexapi.exceptions.NotFound:
            return None

    def _process_season(
        self, show: Show, season: Season, show_review: Optional[str], animapping: AniMap
    ) -> None:
        season_offset = animapping.tvdb_epoffset or 0

        season_episodes = self._get_filtered_episodes(season, season_offset)

        if all(not episode.isPlayed for episode in season_episodes):
            log.debug(
                f"{self.__class__.__name__}: No watched episodes found for show '{show.title}' "
                f"season {season.index}. Skipping"
            )
            return

        # Find corresponding AniList media
        anilist_media = self._find_anilist_media_by_ids(show.title, animapping)
        if not anilist_media:
            return

        # Further filter episodes based on AniList episode count if available
        if anilist_media.episodes:
            episodes = self._filter_episodes_by_count(
                season_episodes, anilist_media.episodes, season_offset
            )
        self._sync_media_data((show, season, episodes), anilist_media, show_review)

    def _get_filtered_episodes(self, season: Season, offset: int) -> list[Episode]:
        return season.episodes(index__gt=offset)

    def _filter_episodes_by_count(
        self, episodes: list[Episode], total_episodes: int, offset: int
    ) -> list[Episode]:
        return [e for e in episodes if e.index <= total_episodes + offset]

    def _determine_watch_status(
        self,
        media_tuple: tuple[Show, Season, list[Episode]],
        anilist_media: AniListMedia,
    ) -> Optional[AniListMediaListStatus]:
        show, season, episodes = media_tuple

        last_watched_episode: Episode = max(
            (e for e in episodes if e.isPlayed),
            key=lambda e: e.lastViewedAt,
            default=None,
        )

        on_deck = False
        on_deck_episode: Episode = season.onDeck()
        if on_deck_episode in episodes:
            on_deck = True

        was_dropped = False
        if (
            not on_deck
            and last_watched_episode != episodes[-1]
            and last_watched_episode.lastViewedAt
            > datetime.now() - timedelta(weeks=self.plex_client.on_deck_window)
        ):
            was_dropped = True

        watched_episodes = [e for e in episodes if e.isPlayed]

        if on_deck:
            return AniListMediaListStatus.CURRENT
        elif watched_episodes and len(watched_episodes) >= anilist_media.episodes:
            return AniListMediaListStatus.COMPLETED
        elif was_dropped:
            return AniListMediaListStatus.DROPPED
        elif show.onWatchlist():
            return AniListMediaListStatus.PLANNING
        else:
            return None

    def _get_plex_season_data(
        self,
        show: Show,
        season: Season,
        episodes: list[Episode],
        anilist_media: AniListMedia,
        show_review: Optional[str],
    ) -> dict[str, Any]:
        return {
            "status": self._determine_watch_status(
                (show, season, episodes), anilist_media
            ),
            "score": season.userRating,
            "progress": sum(1 for e in episodes if e.viewCount),
            "notes": self.plex_client.get_user_review(season) or show_review,
        }

    def _sync_media_data(
        self,
        media_tuple: tuple[Show, Season, list[Episode]],
        anilist_media: AniListMedia,
        show_review: Optional[str] = None,
    ) -> None:
        show, season, episodes = media_tuple

        plex_data = self._get_plex_season_data(
            show, season, episodes, anilist_media, show_review
        )
        anilist_data = self._get_anilist_media_data(anilist_media)

        # Create sync update using base class helper
        to_sync = self._create_sync_update(
            plex_data, anilist_data, fields=["status", "score", "progress", "notes"]
        )

        if len(to_sync):
            self.anilist_client.update_anime_entry(anilist_media.id, **to_sync)
            log.info(
                f"{self.__class__.__name__}: Synced Plex {' and '.join(to_sync.keys())} "
                f"with AniList for show '{show.title}' season {season.seasonNumber} "
                f"{{anilist_id: {anilist_media.id}}}"
            )
