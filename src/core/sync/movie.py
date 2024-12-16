from datetime import datetime, timedelta
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
        if last_synced:  # We're able to do a partial scan
            return section.search(
                # Filter movies that have been updated, viewed, or rated since the last sync
                filters={
                    "or": [
                        {"updatedAt>>=": last_synced},
                        {"lastViewedAt>>=": last_synced},
                        {"lastRatedAt>>=": last_synced},
                    ]
                }
            )
        return section.all()  # Otherwise, we need to do a full scan

    def _process_media_item(self, movie: Movie) -> None:
        title: str = movie.title
        guids = self._format_guids(movie.guids, is_movie=True)

        anilist_media = self._find_anilist_media(title, guids)
        if anilist_media:
            self._sync_media_data(movie, anilist_media)

    def _find_anilist_media(self, title: str, guids: dict) -> Optional[AniListMedia]:
        animappings = self.animap_client.get_mappings(**guids)  # Search by GUIDs first

        if not animappings:  # Fallback to searching by title
            return self._search_by_title(title, episode_count=1)  # Movies are 1 episode

        animapping = animappings[0]  # The first mapping is typically the correct one
        if len(animappings) > 1:
            log.debug(
                f"{self.__class__.__name__}: Multiple mappings found for movie '{title}', using the first one"
            )

        anilist_media = self.find_anilist_media_by_ids(title, animapping)
        return (
            anilist_media
            if anilist_media
            else self._search_by_title(title, episode_count=1)
        )

    def _determine_watch_status(self, movie: Movie) -> Optional[AniListMediaListStatus]:
        on_deck = self.plex_client.is_on_deck(movie)
        was_dropped = False
        if not on_deck and movie.lastViewedAt > datetime.now() - timedelta(
            weeks=self.plex_client.on_deck_window
        ):
            was_dropped = True

        if movie.isPlayed:
            return AniListMediaListStatus.COMPLETED
        elif movie.onWatchlist():
            return AniListMediaListStatus.PLANNING
        elif was_dropped:
            return AniListMediaListStatus.DROPPED
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
            "progress": 1 if movie.viewCount >= 1 else 0,
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
