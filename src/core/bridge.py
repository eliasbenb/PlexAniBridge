"""Bridge Client Module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from plexapi.library import MovieSection, ShowSection
from src import log
from src.config.database import db
from src.config.settings import PlexAnibridgeConfig, PlexAnibridgeProfileConfig
from src.core import AniListClient, AniMapClient, PlexClient
from src.core.sync import (
    BaseSyncClient,
    MovieSyncClient,
    ShowSyncClient,
)
from src.core.sync.base import ParsedGuids
from src.core.sync.stats import SyncStats
from src.models.db.housekeeping import Housekeeping
from src.models.db.sync_history import SyncOutcome

__all__ = ["BridgeClient"]


class BridgeClient:
    """Single-profile bridge client for synchronizing Plex and AniList libraries.

    This class manages the synchronization process for one Plex user with one AniList
    account, using the settings from a single profile configuration.

    Args:
        profile_name (str): Name of the sync profile
        profile_config (PlexAnibridgeProfileConfig): Profile-specific configuration
                                                     settings
        global_config (PlexAnibridgeConfig): Global application configuration
        shared_animap_client (AniMapClient): Shared anime mapping client

    Attributes:
        profile_name (str): Name of the sync profile
        profile_config (PlexAnibridgeProfileConfig): Profile-specific configuration
        global_config (PlexAnibridgeConfig): Global configuration
        animap_client (AniMapClient): Shared anime mapping client
        anilist_client (AniListClient): AniList API client for this profile
        plex_client (PlexClient): Plex API client for this profile
        last_synced (datetime | None): Timestamp of last successful sync
    """

    def __init__(
        self,
        profile_name: str,
        profile_config: PlexAnibridgeProfileConfig,
        global_config: PlexAnibridgeConfig,
        shared_animap_client: AniMapClient,
    ) -> None:
        """Initialize the single-profile BridgeClient.

        Args:
            profile_name (str): Name of the sync profile
            profile_config (PlexAnibridgeProfileConfig): Profile-specific configuration
                                                         settings
            global_config (PlexAnibridgeConfig): Global application configuration
            shared_animap_client (AniMapClient): Shared anime mapping client
        """
        self.profile_name = profile_name
        self.profile_config = profile_config
        self.global_config = global_config
        self.animap_client = shared_animap_client

        self.anilist_client = AniListClient(
            anilist_token=profile_config.anilist_token,
            backup_dir=profile_config.data_path / "backups",
            dry_run=profile_config.dry_run,
        )

        self.plex_client = PlexClient(
            plex_token=profile_config.plex_token,
            plex_user=profile_config.plex_user,
            plex_url=profile_config.plex_url,
            plex_sections=profile_config.plex_sections,
            plex_genres=profile_config.plex_genres,
            plex_metadata_source=profile_config.plex_metadata_source,
        )

        self.last_synced = self._get_last_synced()

    async def initialize(self) -> None:
        """Initialize the bridge client with async setup.

        This should be called after creating the bridge instance.
        """
        log.info(
            f"{self.__class__.__name__}: [{self.profile_name}] Initializing bridge "
            "client"
        )

        self.plex_client.clear_cache()
        await self.anilist_client.initialize()

        log.info(
            f"{self.__class__.__name__}: [{self.profile_name}] Bridge client "
            f"initialized for Plex user $$'{self.profile_config.plex_user}'$$ -> "
            f"AniList user $$'{self.anilist_client.user.name}'$$"
        )

    async def close(self) -> None:
        """Close all async clients."""
        log.debug(
            f"{self.__class__.__name__}: [{self.profile_name}] Closing bridge client"
        )
        await self.anilist_client.close()
        await self.plex_client.close()

    async def __aenter__(self) -> BridgeClient:
        """Context manager enter method.

        Returns:
            BridgeClient: The initialized bridge client instance.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit method.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Traceback object if an exception occurred.
        """
        await self.close()

    def _get_last_synced_key(self) -> str:
        """Generate the database key for this profile's last sync timestamp.

        Returns:
            str: Database key for last sync timestamp
        """
        return f"last_synced_{self.profile_name}"

    def _get_last_synced(self) -> datetime | None:
        """Retrieves the timestamp of the last successful sync from the database.

        Returns:
            datetime | None: UTC timestamp of the last sync, None if never synced

        Note:
            Used to determine whether polling scanning is possible and
            to filter items for incremental syncs
        """
        with db as ctx:
            last_synced = ctx.session.get(Housekeeping, self._get_last_synced_key())
            if last_synced is None or last_synced.value is None:
                return None
            return datetime.fromisoformat(last_synced.value)

    def _set_last_synced(self, last_synced: datetime) -> None:
        """Stores the timestamp of a successful sync in the database.

        Args:
            last_synced (datetime): UTC timestamp to store

        Note:
            Only called after a completely successful sync operation
        """
        self.last_synced = last_synced
        with db as ctx:
            ctx.session.merge(
                Housekeeping(
                    key=self._get_last_synced_key(), value=last_synced.isoformat()
                )
            )
            ctx.session.commit()

    async def sync(
        self, poll: bool = False, rating_keys: list[str] | None = None
    ) -> None:
        """Initiates the synchronization process for this profile.

        This is the main entry point for the sync process. It:
        1. Determines the appropriate sync mode (polling/partial/full, destructive/not)
        2. Processes the configured Plex sections
        3. Updates sync metadata upon successful completion

        Args:
            poll (bool): Flag to enable polling scan mode, default False
            rating_keys (list[str] | None): Optional list of Plex rating keys to
                restrict the sync to.
        """
        log.info(
            f"{self.__class__.__name__}: [{self.profile_name}] Starting "
            f"{'full ' if self.profile_config.full_scan else 'partial '}"
            f"{'and destructive ' if self.profile_config.destructive_sync else ''}"
            f"sync for Plex user $$'{self.profile_config.plex_user}'$$ "
            f"-> AniList user $$'{self.anilist_client.user.name}'$$"
        )

        sync_start_time = datetime.now(UTC)

        movie_sync = MovieSyncClient(
            anilist_client=self.anilist_client,
            animap_client=self.animap_client,
            plex_client=self.plex_client,
            excluded_sync_fields=self.profile_config.excluded_sync_fields,
            full_scan=self.profile_config.full_scan,
            destructive_sync=self.profile_config.destructive_sync,
            search_fallback_threshold=self.profile_config.search_fallback_threshold,
            batch_requests=self.profile_config.batch_requests,
            profile_name=self.profile_name,
        )

        show_sync = ShowSyncClient(
            anilist_client=self.anilist_client,
            animap_client=self.animap_client,
            plex_client=self.plex_client,
            excluded_sync_fields=self.profile_config.excluded_sync_fields,
            full_scan=self.profile_config.full_scan,
            destructive_sync=self.profile_config.destructive_sync,
            search_fallback_threshold=self.profile_config.search_fallback_threshold,
            batch_requests=self.profile_config.batch_requests,
            profile_name=self.profile_name,
        )

        plex_sections = self.plex_client.get_sections()
        sync_stats = SyncStats()

        try:
            for section in plex_sections:
                section_stats = await self._sync_section(
                    section, poll, movie_sync, show_sync, rating_keys=rating_keys
                )
                sync_stats = sync_stats.combine(section_stats)

            sync_completion_time = datetime.now(UTC)
            duration = sync_completion_time - sync_start_time

            self._set_last_synced(sync_start_time)

            log.info(
                f"{self.__class__.__name__}: [{self.profile_name}] Sync completed: "
                f"{sync_stats.synced} synced, {sync_stats.deleted} deleted, "
                f"{sync_stats.skipped} skipped, {sync_stats.not_found} not found, "
                f"{sync_stats.failed} failed. Coverage: {sync_stats.coverage:.2%} "
                f"({len(sync_stats.get_grandchild_items_by_outcome())} total) "
                f"in {duration.total_seconds():.2f} seconds"
            )

            unprocessed_items = sync_stats.get_grandchild_items_by_outcome(
                SyncOutcome.PENDING
            )
            if unprocessed_items:
                log.debug(
                    f"{self.__class__.__name__}: [{self.profile_name}] "
                    f"Unprocessed items: {
                        ', '.join([repr(i) for i in unprocessed_items])
                    }"
                )

        except Exception as e:
            end_time = datetime.now(UTC)
            duration = end_time - sync_start_time

            log.error(
                f"{self.__class__.__name__}: [{self.profile_name}] Sync failed after "
                f"{duration.total_seconds():.2f} seconds: {e}",
                exc_info=True,
            )
            raise

    async def _sync_section(
        self,
        section: MovieSection | ShowSection,
        poll: bool,
        movie_sync: MovieSyncClient,
        show_sync: ShowSyncClient,
        rating_keys: list[str] | None = None,
    ) -> SyncStats:
        """Synchronizes a single Plex library section.

        Args:
            section (MovieSection | ShowSection): Plex library section to process
            poll (bool): Flag to enable polling scan mode
            movie_sync (MovieSyncClient): Movie sync client
            show_sync (ShowSyncClient): Show sync client
            rating_keys (list[str] | None): Optional list of Plex rating keys to
                restrict sync to for this section.

        Returns:
            SyncStats: Statistics about the sync operation for the section
        """
        log.info(
            f"{self.__class__.__name__}: [{self.profile_name}] Syncing "
            f"section $$'{section.title}'$$"
        )

        min_last_modified = (self.last_synced or datetime.now(UTC)) - timedelta(
            seconds=15
        )

        items = list(
            self.plex_client.get_section_items(
                section,
                min_last_modified=min_last_modified if poll else None,
                require_watched=not self.profile_config.full_scan,
                rating_keys=rating_keys,
            )
        )

        if self.profile_config.batch_requests:
            parsed_guids = [ParsedGuids.from_guids(item.guids) for item in items]
            imdb_ids = [guid.imdb for guid in parsed_guids if guid.imdb is not None]
            tmdb_ids = [guid.tmdb for guid in parsed_guids if guid.tmdb is not None]
            tvdb_ids = [guid.tvdb for guid in parsed_guids if guid.tvdb is not None]

            animappings = list(
                self.animap_client.get_mappings(
                    imdb_ids, tmdb_ids, tvdb_ids, is_movie=section.type != "show"
                )
            )
            anilist_ids = [
                a.anilist_id for a in animappings if a.anilist_id is not None
            ]

            log.info(
                f"{self.__class__.__name__}: [{self.profile_name}] Prefetching "
                f"{len(anilist_ids)} entries from the AniList API in batch requests"
                f"(this may take a while)"
            )

            await self.anilist_client.batch_get_anime(anilist_ids)

        sync_client: BaseSyncClient = {
            "movie": movie_sync,
            "show": show_sync,
        }[section.type]

        for item in items:
            try:
                await sync_client.process_media(item)

            except Exception:
                log.error(
                    f"{self.__class__.__name__}: [{self.profile_name}] Failed "
                    f"to sync item $$'{item.title}'$$",
                    exc_info=True,
                )

        if self.profile_config.batch_requests:
            await sync_client.batch_sync()

        return sync_client.sync_stats
