from datetime import datetime
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
        if last_synced is not None:
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
        for attr in ("_pab__review", "_pab__onWatchList"):
            setattr(show, attr, None)

        guids = self._format_guids(show.guids, is_movie=False)

        animappings = self.animap_client.get_mappings(**guids)

        if len(animappings) == 0:
            log.debug(
                f"{self.__class__.__name__}: No mappings found for show '{show.title}'"
            )
            return

        log.debug(
            f"{self.__class__.__name__}: Found {len(animappings)} mappings for show '{show.title}' "
            f"{{anidb_id: {[am.anidb_id for am in animappings]}}}"
        )

        show_review = self.plex_client.get_user_review(show)

        setattr(show, "_pab__review", show_review)
        setattr(show, "_pab__onWatchList", show.onWatchlist())

        for animapping in animappings:
            self._process_show_mapping(show, animapping)

    def _process_show_mapping(self, show: Show, animapping: AniMap) -> None:
        if not animapping.tvdb_season:
            return

        try:
            season = self._get_season(show, animapping.tvdb_season)
            if season is not None:
                anilist_media = self.find_anilist_media_by_ids(show.title, animapping)
                if not anilist_media:
                    return

                self._process_season(show, season, animapping, anilist_media)
            else:
                log.debug(
                    f"{self.__class__.__name__}: Season {animapping.tvdb_season} not found for show '{show.title}'"
                )
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
        self,
        show: Show,
        season: Season,
        animapping: AniMap,
        anilist_media: AniListMedia,
    ) -> None:
        for attr in (
            "_pab__review",
            "_pab__onDeck",
            "_pab__onContinueWatching",
            "_pab__isDropped",
        ):
            setattr(season, attr, None)

        season_offset = animapping.tvdb_epoffset or 0

        if season.viewedLeafCount == 0:
            log.debug(
                f"{self.__class__.__name__}: Season {season.index} has no watched episodes for show '{show.title}'. Skipping"
            )

        if anilist_media.episodes:
            episodes = season.episodes(
                filters={
                    "index>>=": season_offset,
                    "index<=": season_offset + anilist_media.episodes,
                }
            )
        else:
            episodes = season.episodes(index__gt=season_offset)

        season_review = self.plex_client.get_user_review(season)
        continue_watching_episodes = self.plex_client.get_continue_watching(season)

        setattr(season, "_pab_review", season_review)
        setattr(
            season,
            "_pab__onContinueWatching",
            any(e in episodes for e in continue_watching_episodes),
        )
        setattr(season, "_pab__onDeck", season.onDeck() in episodes)
        setattr(
            season,
            "_pab__isDropped",
            (
                not season._pab__onContinueWatching
                and len(episodes) >= anilist_media.episodes
                and len(episodes) < season.leafCount
                and any(e.isPlayed for e in episodes)
            ),
        )

        self._sync_media_data((show, season, episodes), anilist_media)

    def _determine_watch_status(
        self,
        media_tuple: tuple[Show, Season, list[Episode]],
        anilist_media: AniListMedia,
    ) -> Optional[AniListMediaListStatus]:
        show, season, episodes = media_tuple

        watched_episodes = [e for e in episodes if e.isPlayed]

        if season._pab__onContinueWatching:
            return AniListMediaListStatus.CURRENT
        elif len(watched_episodes) >= anilist_media.episodes:
            return AniListMediaListStatus.COMPLETED
        elif show._pab__onWatchList and season._pab__isDropped:
            return AniListMediaListStatus.PAUSED
        elif season._pab__isDropped:
            return AniListMediaListStatus.DROPPED
        elif show._pab__onWatchList:
            return AniListMediaListStatus.PLANNING
        else:
            return None

    def _get_plex_season_data(
        self,
        media_tuple: tuple[Show, Season, list[Episode]],
        anilist_media: AniListMedia,
    ) -> dict[str, Any]:
        show, season, episodes = media_tuple

        return {
            "status": self._determine_watch_status(media_tuple, anilist_media),
            "score": season.userRating,
            "progress": sum(1 for e in episodes if e.isPlayed),
            "notes": season._pab__review or show._pab__review,
        }

    def _sync_media_data(
        self,
        media_tuple: tuple[Show, Season, list[Episode]],
        anilist_media: AniListMedia,
    ) -> None:
        show, season, episodes = media_tuple

        plex_data = self._get_plex_season_data(media_tuple, anilist_media)
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
