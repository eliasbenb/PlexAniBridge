from datetime import datetime
from typing import Optional

from plexapi.library import MovieSection
from plexapi.video import Movie, MovieHistory

from src import log
from src.models.anilist import (
    AniListFuzzyDate,
    AniListMedia,
    AniListMediaListStatus,
)

from .base import BaseSyncClient


class MovieSyncClient(BaseSyncClient[Movie, MovieSection]):
    def _get_media_to_sync(
        self, section: MovieSection, last_synced: Optional[datetime]
    ) -> list[Movie]:
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

    def _process_media_item(self, movie: Movie) -> None:
        for attr in ("_pab__review", "_pab__onWatchList"):
            setattr(movie, attr, None)

        guids = self._format_guids(movie.guids, is_movie=True)

        anilist_media = self._find_anilist_media(movie, guids)

        if anilist_media is None:
            return

        self._sync_media_data(movie, anilist_media)

    def _find_anilist_media(self, movie: Movie, guids: dict) -> Optional[AniListMedia]:
        animappings = self.animap_client.get_mappings(**guids)

        if len(animappings) == 0:
            return self._search_by_title(movie.title, episode_count=1)

        animapping = animappings[0]
        log.debug(
            f"{self.__class__.__name__}: Multiple mappings found for movie '{movie.title}', using the first one"
        )

        anilist_media = self.find_anilist_media_by_ids(
            movie.title, animapping
        ) or self._search_by_title(movie.title, episode_count=1)

        return anilist_media

    def _determine_watch_status(self, movie: Movie) -> Optional[AniListMediaListStatus]:
        on_watchlist = movie.onWatchlist()
        on_continue_watching = self.plex_client.get_continue_watching(movie)
        is_dropped = not on_continue_watching and movie.viewOffset > 0

        if movie.isPlayed and on_continue_watching:
            return AniListMediaListStatus.REPEATING
        elif on_continue_watching:
            return AniListMediaListStatus.PAUSED
        elif movie.isPlayed:
            return AniListMediaListStatus.COMPLETED
        elif on_watchlist and is_dropped:
            return AniListMediaListStatus.PAUSED
        elif is_dropped:
            return AniListMediaListStatus.DROPPED
        elif on_watchlist:
            return AniListMediaListStatus.PLANNING
        else:
            return None

    def _get_plex_movie_data(self, movie: Movie) -> dict:
        watch_history: list[MovieHistory] = movie.history()

        start_date = None
        end_date = None
        if watch_history:
            d1 = watch_history[0].viewedAt
            d2 = watch_history[-1].viewedAt
            start_date = AniListFuzzyDate(year=d1.year, month=d1.month, day=d1.day)
            end_date = AniListFuzzyDate(year=d2.year, month=d2.month, day=d2.day)

        return {
            "status": self._determine_watch_status(movie),
            "score": movie.userRating,
            "progress": 1 if movie.isPlayed else None,
            "repeat": movie.viewCount - 1 if movie.viewCount > 1 else None,
            "notes": self.plex_client.get_user_review(movie),
            "start_date": start_date,
            "end_date": end_date,
        }

    def _sync_media_data(self, movie: Movie, anilist_media: AniListMedia) -> None:
        plex_data = self._get_plex_movie_data(movie)
        anilist_data = self._get_anilist_media_data(anilist_media)

        to_sync = self._create_sync_update(
            plex_data,
            anilist_data,
            fields=["status", "score", "repeat", "notes", "start_date", "end_date"],
            additional_conditions={
                "start_date": plex_data["start_date"] is not None,
                "end_date": plex_data["end_date"] is not None,
            },
        )

        if to_sync:
            self.anilist_client.update_anime_entry(
                anilist_media.id,
                progress=1,  # Movies always have progress=1 when watched
                **to_sync,
            )
            log.info(
                f"{self.__class__.__name__}: Synced Plex {' and '.join(to_sync.keys())} "
                f"with AniList for movie '{movie.title}' {{anilist_id: {anilist_media.id}}}"
            )
