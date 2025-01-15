from datetime import datetime

from plexapi.library import MovieSection, ShowSection
from sqlmodel import Session

from src import log
from src.core import AniListClient, AniMapClient, PlexClient
from src.core.sync import MovieSyncClient, ShowSyncClient, SyncStats
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

    The client supports multiple user pairs (Plex user + AniList token), partial scanning
    for efficiency, and both destructive and non-destructive sync modes.

    Attributes:
        config (PlexAnibridgeConfig): Application configuration settings
        token_user_pairs (list[tuple[str, str]]): Paired AniList tokens and Plex usernames
        animap_client (AniMapClient): Client for anime ID mapping database
        last_synced (datetime | None): Timestamp of the last successful sync
        last_config_encoded (str | None): Encoded version of the last used configuration

    Configuration Options:
        - PARTIAL_SCAN: Enable incremental syncs based on modification time
        - DESTRUCTIVE_SYNC: Allow deletion of AniList entries
        - EXCLUDED_SYNC_FIELDS: Fields to ignore during sync
        - FUZZY_SEARCH_THRESHOLD: Matching threshold for title comparison
    """

    def __init__(self, config: PlexAnibridgeConfig) -> None:
        self.config = config
        self.token_user_pairs = list(zip(config.ANILIST_TOKEN, config.PLEX_USER))
        self.animap_client = AniMapClient(config.DATA_PATH)

        self.last_synced = self._get_last_synced()
        self.last_config_encoded = self._get_last_config_encoded()

    def _get_last_synced(self) -> datetime | None:
        """Retrieves the timestamp of the last successful sync from the database.

        Returns:
            datetime | None: Timestamp of the last sync, None if never synced

        Note:
            Used to determine whether partial scanning is possible and
            to filter items for incremental syncs
        """
        with Session(db.engine) as session:
            last_synced = session.get(Housekeeping, "last_synced")
            if last_synced is None or last_synced.value is None:
                return None
            return datetime.fromisoformat(last_synced.value)

    def _set_last_synced(self, last_synced: datetime) -> None:
        """Stores the timestamp of a successful sync in the database.

        Args:
            last_synced (datetime): Timestamp to store

        Note:
            Only called after a completely successful sync operation
        """
        with Session(db.engine) as session:
            session.merge(
                Housekeeping(key="last_synced", value=last_synced.isoformat())
            )
            session.commit()

    def _get_last_config_encoded(self) -> str | None:
        """Retrieves the encoded configuration from the last sync.

        The encoded configuration is used to determine if settings have
        changed between syncs, which affects partial scan eligibility.

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
            Used in conjunction with last_synced to validate partial scan eligibility
        """
        with Session(db.engine) as session:
            session.merge(Housekeeping(key="last_config_encoded", value=config_encoded))
            session.commit()

    def sync(self) -> None:
        """Initiates the synchronization process for all configured user pairs.

        This is the main entry point for the sync process. It:
        1. Determines the appropriate sync mode (partial/full, destructive/non-destructive)
        2. Processes each Plex user + AniList token pair
        3. Updates sync metadata upon successful completion

        The sync process is considered successful only if all user pairs
        are processed without errors. A failure for any user will prevent
        the last_synced timestamp from being updated.

        Note:
            - Partial sync requires valid last_synced and matching configuration
            - Destructive sync can remove entries from AniList
            - Non-destructive sync only processes watched content
        """
        log.info(
            f"{self.__class__.__name__}: Starting "
            f"{'partial ' if self._should_perform_partial_scan() else ''}"
            f"{'and ' if self._should_perform_partial_scan() and self.config.DESTRUCTIVE_SYNC else ''}"
            f"{'destructive ' if self.config.DESTRUCTIVE_SYNC else ''}"
            f"sync between Plex and AniList libraries"
        )

        tmp_last_synced = datetime.now()  # We'll store this if the sync is successful

        for anilist_token, plex_user in self.token_user_pairs:
            self._sync_user(anilist_token, plex_user)

        self._set_last_synced(tmp_last_synced)
        self._set_last_config_encoded(self.config.encode())

        log.info(f"{self.__class__.__name__}: Sync completed")

    def _sync_user(self, anilist_token: str, plex_user: str) -> None:
        """Synchronizes a single Plex user's library with their AniList account.

        Args:
            anilist_token (str): Authentication token for AniList API
            plex_user (str): Username or email of the Plex user

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
        self.anilist_client = AniListClient(
            anilist_token, self.config.DATA_PATH / "backups", self.config.DRY_RUN
        )

        log.info(
            f"{self.__class__.__name__}: Syncing Plex user $$'{plex_user}'$$ "
            f"with AniList user $$'{self.anilist_client.user.name}'$$"
        )

        self.plex_client = PlexClient(
            self.config.PLEX_TOKEN,
            plex_user,
            self.config.PLEX_URL,
            self.config.PLEX_SECTIONS,
        )

        sync_client_args = {
            "anilist_client": self.anilist_client,
            "animap_client": self.animap_client,
            "plex_client": self.plex_client,
            "excluded_sync_fields": self.config.EXCLUDED_SYNC_FIELDS,
            "destructive_sync": self.config.DESTRUCTIVE_SYNC,
            "fuzzy_search_threshold": self.config.FUZZY_SEARCH_THRESHOLD,
        }

        self.movie_sync = MovieSyncClient(**sync_client_args)
        self.show_sync = ShowSyncClient(**sync_client_args)

        plex_sections = self.plex_client.get_sections()

        sync_stats = SyncStats()
        for section in plex_sections:
            sync_stats += self._sync_section(section)

        log.info(
            f"{self.__class__.__name__}: {sync_stats.synced} items synced, {sync_stats.deleted} items deleted, "
            f"{sync_stats.skipped} items skipped, {sync_stats.failed} items failed"
        )

    def _sync_section(self, section: MovieSection | ShowSection) -> SyncStats:
        """Synchronizes a single Plex library section.

        Args:
            section (MovieSection | ShowSection): Plex library section to process

        Returns:
            SyncStats: Statistics about the sync operation including:
                - Number of items synced
                - Number of items deleted
                - Number of items skipped
                - Number of items that failed

        Process:
        1. Retrieves items from the section based on sync mode:
           - Partial scan: Only items modified since last sync
           - Full scan: All items
           - Non-destructive: Only watched items
        2. Routes each item to appropriate sync client (movie/show)
        3. Collects and returns sync statistics
        """
        log.info(f"{self.__class__.__name__}: Syncing section $$'{section.title}'$$")

        items = self.plex_client.get_section_items(
            section,
            min_last_modified=self.last_synced
            if self._should_perform_partial_scan()
            else None,
            require_watched=not self.config.DESTRUCTIVE_SYNC,
        )

        sync_client = self.movie_sync if section.type == "movie" else self.show_sync
        for item in items:
            sync_client.process_media(item)

        return sync_client.sync_stats

    def _should_perform_partial_scan(self) -> bool:
        """Determines if a partial (incremental) sync is possible.

        A partial scan optimizes the sync process by only processing
        items that have been modified since the last successful sync.

        Returns:
            bool: True if all conditions for partial scan are met:
                1. PARTIAL_SCAN setting is enabled
                2. Last sync timestamp exists
                3. Current configuration matches last sync's configuration

        Note:
            Configuration changes invalidate partial scan eligibility to
            ensure changes in sync settings are properly applied
        """
        return (
            self.config.PARTIAL_SCAN
            and self.last_synced is not None
            and self.last_config_encoded == self.config.encode()
        )
