from datetime import datetime, timedelta, timezone

from plexapi.library import MovieSection, ShowSection
from src import log
from src.config.database import db
from src.config.settings import PlexAnibridgeConfig
from src.core import AniListClient, AniMapClient, PlexClient
from src.core.sync import (
    BaseSyncClient,
    MovieSyncClient,
    ParsedGuids,
    ShowSyncClient,
    SyncStats,
)
from src.models.housekeeping import Housekeeping

__all__ = ["BridgeClient"]


class BridgeClient:
    """Main orchestrator for synchronizing Plex and AniList libraries.

    This class manages the synchronization process between Plex media libraries
    and AniList user accounts, handling multiple user pairs and maintaining
    sync state between operations.

    Args:
        config (PlexAnibridgeConfig): Application configuration settings

    Attributes:
        config (PlexAnibridgeConfig): Application configuration
        token_user_pairs (list[tuple[str, str]]): Paired AniList tokens and Plex users
        animap_client (AniMapClient): Client for anime mapping data
        anilist_clients (dict[str, AniListClient]): Cached AniList clients by token
        plex_clients (dict[str, PlexClient]): Cached Plex clients by user
        last_synced (datetime | None): Timestamp of last successful sync
        last_config_encoded (str | None): Encoded config from last sync
    """

    def __init__(self, config: PlexAnibridgeConfig) -> None:
        """Initialize the BridgeClient.

        Args:
            config (PlexAnibridgeConfig): Application configuration settings
        """
        self.config = config

        self.token_user_pairs = list(zip(config.ANILIST_TOKEN, config.PLEX_USER))
        self.animap_client = AniMapClient(config.DATA_PATH)
        self.anilist_clients: dict[str, AniListClient] = {}
        self.plex_clients: dict[str, PlexClient] = {}

        self.last_synced = self._get_last_synced()
        self.last_config_encoded = self._get_last_config_encoded()

    async def initialize(self) -> None:
        """Initialize the bridge client with async setup.

        This should be called after creating the bridge instance.
        """
        await self.animap_client.initialize()
        for plex_client in self.plex_clients.values():
            plex_client.clear_cache()
        for anilist_client in self.anilist_clients.values():
            await anilist_client.initialize()

    async def close(self) -> None:
        """Close all async clients."""
        await self.animap_client.close()

        for client in self.anilist_clients.values():
            await client.close()

        for client in self.plex_clients.values():
            await client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _get_last_synced(self) -> datetime | None:
        """Retrieves the timestamp of the last successful sync from the database.

        Returns:
            datetime | None: UTC timestamp of the last sync, None if never synced

        Note:
            Used to determine whether polling scanning is possible and
            to filter items for incremental syncs
        """
        with db as ctx:
            last_synced = ctx.session.get(Housekeeping, "last_synced")
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
                Housekeeping(key="last_synced", value=last_synced.isoformat())
            )
            ctx.session.commit()

    def _get_last_config_encoded(self) -> str | None:
        """Retrieves the encoded configuration from the last sync.

        The encoded configuration is used to determine if settings have
        changed between syncs, which affects polling scan eligibility.

        Returns:
            str | None: Encoded configuration string, None if no previous sync
        """
        with db as ctx:
            last_config_encoded = ctx.session.get(Housekeeping, "last_config_encoded")
            if last_config_encoded is None:
                return None
            return last_config_encoded.value

    def _set_last_config_encoded(self, config_encoded: str) -> None:
        """Stores the encoded configuration after a successful sync.

        Args:
            config_encoded (str): Encoded configuration string

        Note:
            Used in conjunction with last_synced to validate polling scan eligibility
        """
        self.last_config_encoded = config_encoded
        with db as ctx:
            ctx.session.merge(
                Housekeeping(key="last_config_encoded", value=config_encoded)
            )
            ctx.session.commit()

    async def sync(self, poll: bool = False) -> None:
        """Initiates the synchronization process for all configured user pairs.

        This is the main entry point for the sync process. It:
        1. Determines the appropriate sync mode (polling/partial/full, destructive/non-destructive)
        2. Processes each Plex user + AniList token pair
        3. Updates sync metadata upon successful completion

        Args:
            poll (bool): Flag to enable polling scan mode, default False
        """
        log.info(
            f"{self.__class__.__name__}: Starting "
            f"{'full ' if self.config.FULL_SCAN else 'partial '}"
            f"{'and destructive ' if self.config.DESTRUCTIVE_SYNC else ''}"
            f"sync between Plex and AniList libraries"
        )

        sync_datetime = datetime.now(timezone.utc)

        for anilist_token, plex_user in self.token_user_pairs:
            await self._sync_user(anilist_token, plex_user, poll)

        self._set_last_synced(sync_datetime)

        config_encoded = self.config.encode()
        if config_encoded != self.last_config_encoded:
            self._set_last_config_encoded(config_encoded)

        log.info(
            f"{self.__class__.__name__}: {'Polling' if poll else 'Periodic'} sync completed"
        )

    async def _sync_user(self, anilist_token: str, plex_user: str, poll: bool) -> None:
        """Synchronizes a single Plex user's library with their AniList account.

        Args:
            anilist_token (str): Authentication token for AniList API
            plex_user (str): Username or email of the Plex user
            poll (bool): Flag to enable polling scan mode
        """
        if plex_user not in self.plex_clients:
            self.plex_clients[plex_user] = PlexClient(
                self.config.PLEX_TOKEN,
                plex_user,
                self.config.PLEX_URL,
                self.config.PLEX_SECTIONS,
                self.config.PLEX_GENRES,
                self.config.PLEX_METADATA_SOURCE,
            )
        plex_client = self.plex_clients[plex_user]

        if anilist_token not in self.anilist_clients:
            anilist_client = AniListClient(
                anilist_token, self.config.DATA_PATH / "backups", self.config.DRY_RUN
            )
            await anilist_client.initialize()
            self.anilist_clients[anilist_token] = anilist_client
        else:
            anilist_client = self.anilist_clients[anilist_token]

        log.info(
            f"{self.__class__.__name__}: Syncing Plex user $$'{plex_user}'$$ "
            f"with AniList user $$'{anilist_client.user.name}'$$"
        )

        self.movie_sync = MovieSyncClient(
            anilist_client=anilist_client,
            animap_client=self.animap_client,
            plex_client=plex_client,
            excluded_sync_fields=self.config.EXCLUDED_SYNC_FIELDS,
            full_scan=self.config.FULL_SCAN,
            destructive_sync=self.config.DESTRUCTIVE_SYNC,
            search_fallback_threshold=self.config.SEARCH_FALLBACK_THRESHOLD,
            batch_requests=self.config.BATCH_REQUESTS,
        )
        self.show_sync = ShowSyncClient(
            anilist_client=anilist_client,
            animap_client=self.animap_client,
            plex_client=plex_client,
            excluded_sync_fields=self.config.EXCLUDED_SYNC_FIELDS,
            full_scan=self.config.FULL_SCAN,
            destructive_sync=self.config.DESTRUCTIVE_SYNC,
            search_fallback_threshold=self.config.SEARCH_FALLBACK_THRESHOLD,
            batch_requests=self.config.BATCH_REQUESTS,
        )

        plex_sections = plex_client.get_sections()

        sync_stats = SyncStats()

        start_time = datetime.now(timezone.utc)
        for section in plex_sections:
            section_stats = await self._sync_section(
                plex_client, anilist_client, section, poll
            )
            sync_stats += section_stats
        end_time = datetime.now(timezone.utc)
        duration = end_time - start_time

        log.info(
            f"{self.__class__.__name__}: Syncing Plex user $$'{plex_user}'$$ to AniList user "
            f"$$'{anilist_client.user.name}'$$ completed"
        )

        # The unsynced items will include anything that failed or was not found
        unsynced_items = list(sync_stats.possible - sync_stats.covered)
        if unsynced_items:
            unsynced_items_str = ", ".join(str(i) for i in sorted(unsynced_items))
            log.debug(
                f"{self.__class__.__name__}: The following items could not be synced: {unsynced_items_str}"
            )

        log.info(
            f"{self.__class__.__name__}: {sync_stats.synced} items synced, {sync_stats.deleted} items deleted, "
            f"{sync_stats.skipped} items skipped, {sync_stats.not_found} items not found, "
            f"and {sync_stats.failed} items failed with a coverage of {sync_stats.coverage:.2%} in "
            f"{duration.total_seconds():.2f} seconds"
        )

    async def _sync_section(
        self,
        plex_client: PlexClient,
        anilist_client: AniListClient,
        section: MovieSection | ShowSection,
        poll: bool,
    ) -> SyncStats:
        """Synchronizes a single Plex library section.

        Args:
            plex_client (PlexClient): Client for the Plex user
            anilist_client (AniListClient): Client for the AniList user
            section (MovieSection | ShowSection): Plex library section to process
            poll (bool): Flag to enable polling scan mode

        Returns:
            SyncStats: Statistics about the sync operation for the section
        """
        log.info(f"{self.__class__.__name__}: Syncing section $$'{section.title}'$$")

        min_last_modified = (
            self.last_synced or datetime.now(timezone.utc)
        ) - timedelta(seconds=15)

        items = list(
            plex_client.get_section_items(
                section,
                min_last_modified=min_last_modified if poll else None,
                require_watched=not self.config.FULL_SCAN,
            )
        )

        if self.config.BATCH_REQUESTS:
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
                f"{self.__class__.__name__}: Prefetching {len(anilist_ids)} entries "
                f"from the AniList API in batch requests (this may take a while)"
            )

            await anilist_client.batch_get_anime(anilist_ids)

        sync_client: BaseSyncClient = {
            "movie": self.movie_sync,
            "show": self.show_sync,
        }[section.type]

        for item in items:
            try:
                await sync_client.process_media(item)

            except Exception:
                log.error(
                    f"{self.__class__.__name__}: Failed to sync item $$'{item.title}'$$",
                    exc_info=True,
                )

        if self.config.BATCH_REQUESTS:
            await sync_client.batch_sync()

        return sync_client.sync_stats
