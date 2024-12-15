from datetime import datetime, timedelta
from typing import Union

import plexapi.exceptions
from plexapi.library import MovieSection, ShowSection
from plexapi.media import Guid
from plexapi.video import Episode, Movie, Season, Show
from thefuzz import fuzz

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.models.anilist import AnilistMedia, AnilistMediaListStatus


class BridgeClient:
    def __init__(
        self,
        dry_run: bool,
        anilist_token: str,
        anilist_user: str,
        animap_sync_interval: int,
        plex_url: str,
        plex_token: str,
        plex_sections: list[str],
        plex_user: str,
        fuzzy_search_threshold: int,
    ):
        self.dry_run = dry_run
        self.animap_sync_interval = animap_sync_interval

        self.anilist_client = AniListClient(anilist_token, anilist_user, dry_run)
        self.animap_client = AniMapClient()
        self.plex_client = PlexClient(plex_url, plex_token, plex_sections, plex_user)

        self.fuzzy_search_threshold = fuzzy_search_threshold

    def sync(self):
        log.info(f"{self.__class__.__name__}: Syncing Plex and AniList libraries")

        plex_sections = self.plex_client.get_sections()

        for section in plex_sections:
            if self.plex_client.is_movie(section):
                self._sync_movies(section)
            elif self.plex_client.is_show(section):
                self._sync_shows(section)

    def _sync_movies(self, section: MovieSection):
        log.debug(
            f"{self.__class__.__name__}: Syncing movies in section '{section.title}'"
        )

        movies: list[Movie] = section.all()
        for movie in movies:
            title: str = movie.title
            guids = self.__format_guids(movie.guids, is_movie=True)

            animappings = self.animap_client.get_mappings(**guids)

            should_title_search = False

            if len(animappings) == 0:
                log.debug(
                    f"{self.__class__.__name__}: No mappings found for movie '{title}'. Attempting to search Anilist for the title"
                )
                should_title_search = True
            else:
                if len(animappings) > 1:
                    log.debug(
                        f"{self.__class__.__name__}: Multiple mappings found for movie '{title}', using the first one {{anidb_id: {animappings[0].anidb_id}}}"
                    )
                else:
                    log.debug(
                        f"{self.__class__.__name__}: Found mapping for movie '{title}' {{anidb_id: {animappings[0].anidb_id}}}"
                    )
                animapping = animappings[0]

                if animapping.anilist_id:
                    anilist_media = self.anilist_client.get_anime(
                        animapping.anilist_id[0]
                    )
                elif animapping.mal_id:
                    log.debug(
                        f"{self.__class__.__name__}: No AniList ID found for movie '{title}'. Attempting to search Anilist for the MAL ID {animapping.mal_id}"
                    )

                    anilist_media = self.anilist_client.get_anime(
                        mal_id=animapping.mal_id[0]
                    )

                    log.debug(
                        f"{self.__class__.__name__}: No matches found for movie '{title}' with the MAL ID {animapping.mal_id}. Attempting to search Anilist for the title"
                    )
                    should_title_search = True
                else:
                    log.debug(
                        f"{self.__class__.__name__}: No AniList ID or MAL ID found for movie '{title}'. Attempting to search Anilist for the title"
                    )
                    should_title_search = True

            if should_title_search:
                anilist_media = self.__fuzzy_search(title, 1)
                if anilist_media is None:
                    log.warning(
                        f"{self.__class__.__name__}: No suitable results found for movie '{title}' using title search. You can try lowering the `FUZZY_SEARCH_THRESHOLD` setting at the risk of possibly matching entries incorrectly. Skipping"
                    )
                    continue

                log.info(
                    f"{self.__class__.__name__}: Matched '{title}' to AniList entry '{anilist_media.best_title}' {{anilist_id: {anilist_media.id}}} with a ratio of {fuzz.ratio(title, anilist_media.best_title)} using title matching"
                )

            self._sync_movie(movie, anilist_media)

    def _sync_movie(self, movie: Movie, anilist_media: AnilistMedia):
        if anilist_media.mediaListEntry is None:
            anilist_status = None
            anilist_rating = None
            anilist_repeat = None
        else:
            anilist_status = anilist_media.mediaListEntry.status or None
            anilist_rating = anilist_media.mediaListEntry.score or None
            anilist_repeat = anilist_media.mediaListEntry.repeat or None

        plex_status: str = (
            AnilistMediaListStatus.COMPLETED
            if movie.viewCount >= 1
            else AnilistMediaListStatus.PLANNING
            if movie.onWatchlist()
            else AnilistMediaListStatus.DROPPED
            if (
                movie.lastViewedAt is not None
                and movie.lastViewedAt > datetime.now() - timedelta(days=90)
            )
            else AnilistMediaListStatus.PAUSED
            if movie.viewOffset is not None and movie.viewOffset > 0
            else None
        )
        plex_rating: Union[float, None] = movie.userRating or None
        plex_repeat: Union[int, None] = (
            movie.viewCount - 1 if movie.viewCount > 1 else None
        ) or None

        if (
            anilist_status == plex_status
            and anilist_rating == plex_rating
            and anilist_repeat == plex_repeat
        ):
            log.debug(
                f"{self.__class__.__name__}: Movie '{movie.title}' already synced with AniList"
            )
            return

        was_synced_arr: list[str] = []
        if (
            plex_status is not None
            and anilist_status is not None
            and plex_status > anilist_status
        ):
            log.debug(
                f"{self.__class__.__name__}: Syncing Plex's watch status with AniList for movie '{movie.title}' {{anilist_id: {anilist_media.id}}} (Plex: {plex_status} -> AniList: {anilist_status})"
            )
            was_synced_arr.append("status")
        if (
            plex_rating is not None
            and anilist_rating is not None
            and plex_rating != anilist_rating
        ):
            log.debug(
                f"{self.__class__.__name__}: Syncing Plex's rating with AniList for movie '{movie.title}' {{anilist_id: {anilist_media.id}}} (Plex: {plex_rating} -> AniList: {anilist_rating})"
            )
            was_synced_arr.append("rating")
        if (
            plex_repeat is not None
            and anilist_repeat is not None
            and plex_repeat != anilist_repeat
        ):
            log.debug(
                f"{self.__class__.__name__}: Syncing Plex's repeat count with AniList for movie '{movie.title}' {{anilist_id: {anilist_media.id}}} (Plex: {plex_repeat} -> AniList: {anilist_repeat})"
            )
            was_synced_arr.append("repeat")

        if len(was_synced_arr) > 0:
            self.anilist_client.update_anime_entry(
                anilist_media.id,
                status=plex_status,
                score=plex_rating,
                progress=1,
            )
            log.info(
                f"{self.__class__.__name__}: Synced Plex {" and ".join(was_synced_arr)} with AniList for movie '{movie.title}' {{anilist_id: {anilist_media.id}}}"
            )

    def _sync_shows(self, section: ShowSection):
        log.debug(
            f"{self.__class__.__name__}: Syncing shows in section '{section.title}'"
        )

        shows: list[Show] = section.all()

        for show in shows:
            title: str = show.title
            guids = self.__format_guids(show.guids, is_movie=False)

            animappings = self.animap_client.get_mappings(**guids)

            should_title_search = False

            if len(animappings) == 0:
                log.debug(
                    f"{self.__class__.__name__}: No mappings found for show '{title}'. Attempting to search Anilist for the title"
                )
                should_title_search = True
            else:
                log.debug(
                    f"{self.__class__.__name__}: Found {len(animappings)} mappings for show '{title}' {{anidb_id: {[am.anidb_id for am in animappings]}}}"
                )

                for animapping in animappings:
                    if not animapping.tvdb_season:
                        continue

                    try:
                        season: Season = show.season(season=animapping.tvdb_season)
                    except plexapi.exceptions.NotFound:
                        continue
                    if season is None:
                        continue

                    season_offset = animapping.tvdb_epoffset or 0

                    season_episodes: list[Episode] = season.episodes(
                        index__gt=season_offset
                    )
                    watched_episodes = [e for e in season_episodes if e.viewCount > 0]

                    if len(watched_episodes) == 0:
                        log.debug(
                            f"{self.__class__.__name__}: No watched episodes found for show '{show.title}' season {season.index}. Skipping"
                        )
                        continue

                    if animapping.anilist_id:
                        anilist_media = self.anilist_client.get_anime(
                            animapping.anilist_id[0]
                        )
                    elif animapping.mal_id:
                        log.debug(
                            f"{self.__class__.__name__}: No AniList ID found for show '{title}'. Attempting to search Anilist for the MAL ID {animapping.mal_id}"
                        )

                        anilist_media = self.anilist_client.get_anime(
                            mal_id=animapping.mal_id[0]
                        )

                        if anilist_media is None:
                            log.debug(
                                f"{self.__class__.__name__}: No matches found for show '{title}' with the MAL ID {animapping.mal_id}. Attempting to search Anilist for the title"
                            )
                            should_title_search = True
                    else:
                        log.debug(
                            f"{self.__class__.__name__}: No AniList ID or MAL ID found for show '{title}'. Attempting to search Anilist for the title"
                        )
                        should_title_search = True

                    if should_title_search:
                        continue

                    if anilist_media and anilist_media.episodes:
                        season_episodes = [
                            e
                            for e in season_episodes
                            if e.index <= anilist_media.episodes + season_offset
                        ]
                        watched_episodes = [
                            e for e in season_episodes if e.viewCount > 0
                        ]

                    self._sync_season(show, season, watched_episodes, anilist_media)

    def _sync_season(
        self,
        show: Show,
        season: Season,
        episodes: list[Episode],
        anilist_media: AnilistMedia,
    ):
        if anilist_media.mediaListEntry is None:
            anilist_status = None
            anilist_rating = None
            anilist_progress = 0
        else:
            anilist_status = anilist_media.mediaListEntry.status or None
            anilist_rating = anilist_media.mediaListEntry.score or None
            anilist_progress = anilist_media.mediaListEntry.progress or 0

        last_watched_episode: Episode = min(
            episodes, key=lambda e: e.viewCount, default=None
        )

        plex_status: str = (
            AnilistMediaListStatus.COMPLETED
            if len(episodes) >= anilist_media.episodes
            else AnilistMediaListStatus.PLANNING
            if show.onWatchlist()
            else AnilistMediaListStatus.DROPPED
            if (
                last_watched_episode.lastViewedAt is not None
                and last_watched_episode.lastViewedAt
                > datetime.now() - timedelta(days=90)
            )
            else AnilistMediaListStatus.PAUSED
            if last_watched_episode.viewOffset > 0
            else None
        )

        plex_rating: Union[float, None] = season.userRating or None
        plex_progress: int = len(episodes)

        if (
            anilist_status == plex_status
            and anilist_rating == plex_rating
            and anilist_progress == plex_progress
        ):
            log.debug(
                f"{self.__class__.__name__}: Show '{show.title}' season {season.seasonNumber} already synced with AniList"
            )
            return

        was_synced_arr: list[str] = []
        if plex_status is not None and (
            (anilist_status is not None and plex_status > anilist_status)
            or anilist_status is None
        ):
            log.debug(
                f"{self.__class__.__name__}: Syncing Plex's watch status with AniList for show '{show.title}' season {season.seasonNumber} {{anilist_id: {anilist_media.id}}} (Plex: {plex_status} -> AniList: {anilist_status})"
            )
            was_synced_arr.append("status")
        if plex_rating is not None and plex_rating != anilist_rating:
            log.debug(
                f"{self.__class__.__name__}: Syncing Plex's rating with AniList for show '{show.title}' season {season.seasonNumber} {{anilist_id: {anilist_media.id}}} (Plex: {plex_rating} -> AniList: {anilist_rating})"
            )
            was_synced_arr.append("rating")
        if plex_progress > 0 and plex_progress > anilist_progress:
            log.debug(
                f"{self.__class__.__name__}: Syncing Plex's progress with AniList for show '{show.title}' season {season.seasonNumber} {{anilist_id: {anilist_media.id}}} (Plex: {plex_progress} -> AniList: {anilist_progress})"
            )
            was_synced_arr.append("progress")

        if len(was_synced_arr) > 0:
            self.anilist_client.update_anime_entry(
                anilist_media.id,
                status=plex_status,
                score=plex_rating,
                progress=plex_progress,
            )
            log.info(
                f"{self.__class__.__name__}: Synced Plex {" and ".join(was_synced_arr)} with AniList for show '{show.title}' season {season.seasonNumber} {{anilist_id: {anilist_media.id}}}"
            )

    def __fuzzy_search(self, search_str: str, episodes: int) -> AnilistMedia:
        search_results = self.anilist_client.search_anime(search_str)

        return next(
            (
                media
                for media in search_results
                if media.episodes == episodes
                and fuzz.ratio(media.best_title, search_str)
                >= self.fuzzy_search_threshold
            ),
            None,
        )

    def __format_guids(
        self, guids: list[Guid], is_movie: bool
    ) -> dict[str, Union[int, str]]:
        formatted_guids = {
            "tmdb_movie_id": None,
            "tmdb_show_id": None,
            "tvdb_id": None,
            "imdb_id": None,
        }

        for guid in guids:
            if guid.id.startswith("tmdb://"):
                pass
                formatted_guids["tmdb_movie_id" if is_movie else "tmdb_show_id"] = int(
                    guid.id.split("://")[1]
                )
            elif guid.id.startswith("tvdb://"):
                formatted_guids["tvdb_id"] = int(guid.id.split("://")[1])
            elif guid.id.startswith("imdb://"):
                formatted_guids["imdb_id"] = guid.id.split("://")[1]

        return formatted_guids
