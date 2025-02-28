from datetime import datetime, timezone

from plexapi.library import MovieSection, ShowSection
from sqlmodel import Session

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.core.sync import BaseSyncClient, MovieSyncClient, ShowSyncClient, SyncStats
from src.database import db
from src.models.housekeeping import Housekeeping
from src.settings import PlexAnibridgeConfig


class BridgeClient:
    """Main orchestrator for synchronizing Plex and AniList libraries.

    This client serves as the central coordinator for the entire synchronization process,
    managing the initialization and interaction between various components:
    - AniList API client
    - Plex Media Server client
    - AniMap database client (for ID mappings)
    - Sync clients for movies and TV shows

    Attributes:
        config (PlexAnibridgeConfig): Application configuration settings
        token_user_pairs (list[tuple[str, str]]): Paired AniList tokens and Plex usernames
        animap_client (AniMapClient): Client for anime ID mapping database
        last_synced (datetime | None): UTC timestamp of the last successful sync
        last_config_encoded (str | None): Encoded version of the last used configuration

    Configuration Options:
        - FULL_SCAN: Allow scanning items that don't have any activity
        - DESTRUCTIVE_SYNC: Allow deletion of AniList entries
        - EXCLUDED_SYNC_FIELDS: Fields to ignore during sync
        - FUZZY_SEARCH_THRESHOLD: Matching threshold for title comparison

    Args:
        config (PlexAnibridgeConfig): Application configuration settings
    """

    MIN_DATETIME = datetime.min.replace(tzinfo=timezone.utc)

    def __init__(self, config: PlexAnibridgeConfig) -> None:
        """Initialize the AniList client.

        Args:
            anilist_token (str): Authentication token for AniList API access
            backup_dir (Path): Directory path where backup files will be stored
            dry_run (bool): If True, simulates API calls without making actual changes
        """
        self.config = config

        self.token_user_pairs = list(zip(config.ANILIST_TOKEN, config.PLEX_USER))
        self.animap_client = AniMapClient(config.DATA_PATH)
        self.anilist_clients: dict[str, AniListClient] = {}
        self.plex_clients: dict[str, PlexClient] = {}

        self.last_synced = self._get_last_synced()
        self.last_polled = self._get_last_polled()
        self.last_config_encoded = self._get_last_config_encoded()

    def reinit(self) -> None:
        """Reinitializes the Plex and AniList clients to refresh user data during polling.

        Refreshes Plex and AniList user data, clear caches, and reinitialize clients.
        """
        self.animap_client.reinit()
        for plex_client in self.plex_clients.values():
            plex_client.clear_cache()
        for anilist_client in self.anilist_clients.values():
            anilist_client.reinit()

    def _get_last_synced(self) -> datetime | None:
        """Retrieves the timestamp of the last successful sync from the database.

        Returns:
            datetime | None: UTC timestamp of the last sync, None if never synced

        Note:
            Used to determine whether polling scanning is possible and
            to filter items for incremental syncs
        """
        with Session(db.engine) as session:
            last_synced = session.get(Housekeeping, "last_synced")
            if last_synced is None or last_synced.value is None:
                return None
            return datetime.fromisoformat(last_synced.value).replace(
                tzinfo=timezone.utc
            )

    def _get_last_polled(self) -> datetime | None:
        """Retrieves the timestamp of the last polling scan from the database.

        Returns:
            datetime | None: UTC timestamp of the last polling scan, None if never polled

        Note:
            Used to determine whether a polling scan is eligible to run
        """
        with Session(db.engine) as session:
            last_polled = session.get(Housekeeping, "last_polled")
            if last_polled is None or last_polled.value is None:
                return None
            return datetime.fromisoformat(last_polled.value).replace(
                tzinfo=timezone.utc
            )

    def _set_last_synced(self, last_synced: datetime) -> None:
        """Stores the timestamp of a successful sync in the database.

        Args:
            last_synced (datetime): UTC timestamp to store

        Note:
            Only called after a completely successful sync operation
        """
        self.last_synced = last_synced
        with Session(db.engine) as session:
            session.merge(
                Housekeeping(key="last_synced", value=last_synced.isoformat())
            )
            session.commit()

    def _set_last_polled(self, last_polled: datetime) -> None:
        """Stores the timestamp of a polling scan in the database.

        Args:
            last_polled (datetime): UTC timestamp to store

        Note:
            Only called after a successful polling scan
        """
        self.last_polled = last_polled
        with Session(db.engine) as session:
            session.merge(
                Housekeeping(key="last_polled", value=last_polled.isoformat())
            )
            session.commit()

    def _get_last_config_encoded(self) -> str | None:
        """Retrieves the encoded configuration from the last sync.

        The encoded configuration is used to determine if settings have
        changed between syncs, which affects polling scan eligibility.

        Returns:
            str | None: Encoded configuration string, None if no previous sync
        """
        with Session(db.engine) as session:
            last_config_encoded = session.get(Housekeeping, "last_config_encoded")
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
        with Session(db.engine) as session:
            session.merge(Housekeeping(key="last_config_encoded", value=config_encoded))
            session.commit()

    def sync(self, poll: bool = False) -> None:
        """Initiates the synchronization process for all configured user pairs.

        This is the main entry point for the sync process. It:
        1. Determines the appropriate sync mode (polling/partial/full, destructive/non-destructive)
        2. Processes each Plex user + AniList token pair
        3. Updates sync metadata upon successful completion

        The sync process is considered successful only if all user pairs
        are processed without errors. A failure for any user will prevent
        the last_synced timestamp from being updated.

        Note:
            - Polling scan requires valid last_synced and matching configuration
            - Partial scan can process only items with some Plex activity
            - Full scan can process all items in the library
            - Destructive sync can remove entries from AniList

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
            self._sync_user(anilist_token, plex_user, poll)

        if poll:
            self._set_last_polled(sync_datetime)
        else:
            self._set_last_synced(sync_datetime)

        config_encoded = self.config.encode()
        if config_encoded != self.last_config_encoded:
            self._set_last_config_encoded(config_encoded)

        log.info(
            f"{self.__class__.__name__}: {'Polling' if poll else 'Periodic'} sync completed"
        )

    def _sync_user(self, anilist_token: str, plex_user: str, poll: bool) -> None:
        """Synchronizes a single Plex user's library with their AniList account.

        Args:
            anilist_token (str): Authentication token for AniList API
            plex_user (str): Username or email of the Plex user
            poll (bool): Flag to enable polling scan mode

        Process:
        1. Initializes AniList client with user's token
        2. Initializes Plex client for the user
        3. Creates sync clients for movies and shows
        4. Processes each configured Plex section
        5. Reports sync statistics

        Note:
            Creates new client instances for each user to maintain proper
            authentication and separation of concerns
        """
        if plex_user not in self.plex_clients:
            self.plex_clients[plex_user] = PlexClient(
                self.config.PLEX_TOKEN,
                plex_user,
                self.config.PLEX_URL,
                self.config.PLEX_SECTIONS,
            )
        plex_client = self.plex_clients[plex_user]

        if anilist_token not in self.anilist_clients:
            self.anilist_clients[anilist_token] = AniListClient(
                anilist_token, self.config.DATA_PATH / "backups", self.config.DRY_RUN
            )
        anilist_client = self.anilist_clients[anilist_token]

        log.info(
            f"{self.__class__.__name__}: Syncing Plex user $$'{plex_user}'$$ "
            f"with AniList user $$'{anilist_client.user.name}'$$"
        )

        sync_client_args = {
            "anilist_client": anilist_client,
            "animap_client": self.animap_client,
            "plex_client": plex_client,
            "excluded_sync_fields": self.config.EXCLUDED_SYNC_FIELDS,
            "full_scan": self.config.FULL_SCAN,
            "destructive_sync": self.config.DESTRUCTIVE_SYNC,
            "fuzzy_search_threshold": self.config.FUZZY_SEARCH_THRESHOLD,
        }

        self.movie_sync = MovieSyncClient(**sync_client_args)
        self.show_sync = ShowSyncClient(**sync_client_args)

        plex_sections = plex_client.get_sections()

        sync_stats = SyncStats()
        for section in plex_sections:
            sync_stats += self._sync_section(plex_client, section, poll)

        log.info(
            f"{self.__class__.__name__}: Syncing Plex user $$'{plex_user}'$$ to AniList user "
            f"$$'{anilist_client.user.name}'$$ completed"
        )

        unsynced_items = sorted(
            list(sync_stats.possible - sync_stats.covered),
            key=lambda x: (x.type, x.parentRatingKey, x.parentIndex, x.index),
        )
        unsynced_items_str = ", ".join(str(i) for i in unsynced_items)
        log.debug(
            f"{self.__class__.__name__}: The following items could not be synced: {unsynced_items_str}"
        )

        log.info(
            f"{self.__class__.__name__}: {sync_stats.synced} items synced, {sync_stats.deleted} items deleted, "
            f"{sync_stats.skipped} items skipped, {sync_stats.not_found} items not found, "
            f"and {sync_stats.failed} items failed with a coverage of {sync_stats.coverage:.2%}"
        )

    def _sync_section(
        self, plex_client: PlexClient, section: MovieSection | ShowSection, poll: bool
    ) -> SyncStats:
        """Synchronizes a single Plex library section.

        Args:
            plex_client (PlexClient): Client for the Plex user
            section (MovieSection | ShowSection): Plex library section to process
            poll (bool): Flag to enable polling scan mode

        Returns:
            SyncStats: Statistics about the sync operation including:
                - Number of items synced
                - Number of items deleted
                - Number of items skipped
                - Number of items that failed

        Process:
        1. Retrieves items from the section based on sync mode:
           - Partial scan: Only items with activity
           - Full scan: All items
           - Non-destructive: Only watched items
        2. Routes each item to appropriate sync client (movie/show)
        3. Collects and returns sync statistics
        """
        log.info(f"{self.__class__.__name__}: Syncing section $$'{section.title}'$$")

        last_sync = max(
            self.last_synced or self.MIN_DATETIME,
            self.last_polled or self.MIN_DATETIME,
        )
        last_sync = (
            datetime.now(timezone.utc) if last_sync == self.MIN_DATETIME else last_sync
        )
        items = plex_client.get_section_items(
            section,
            min_last_modified=last_sync if poll else None,
            require_watched=not self.config.FULL_SCAN,
        )

        sync_client: BaseSyncClient = {
            "movie": self.movie_sync,
            "show": self.show_sync,
        }[section.type]
        for item in items:
            try:
                sync_client.process_media(item)
            except Exception:
                log.error(
                    f"{self.__class__.__name__}: Failed to sync item $$'{item.title}'$$: ",
                    exc_info=True,
                )

        return sync_client.sync_stats
