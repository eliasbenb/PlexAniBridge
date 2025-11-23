"""Bridge Client Module."""

import contextlib
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from anibridge_providers.library import (
    ExternalId,
    LibraryMedia,
    LibraryProvider,
    LibrarySection,
    MediaKind,
)
from anibridge_providers.list import ListProvider
from starlette.requests import Request

from src import log
from src.config.database import db
from src.config.settings import AniBridgeConfig, AniBridgeProfileConfig
from src.core.animap import AniMapClient
from src.core.sync import BaseSyncClient, MovieSyncClient, ShowSyncClient
from src.core.sync.stats import SyncOutcome, SyncProgress, SyncStats
from src.models.db.housekeeping import Housekeeping
from src.providers.factory import build_library_provider, build_list_provider

__all__ = ["BridgeClient"]


class BridgeClient:
    """Single-profile bridge client that coordinates provider synchronization."""

    def __init__(
        self,
        profile_name: str,
        profile_config: AniBridgeProfileConfig,
        global_config: AniBridgeConfig,
        shared_animap_client: AniMapClient,
    ) -> None:
        """Initialize the bridge client for a single profile.

        Args:
            profile_name (str): The name of the profile.
            profile_config (AniBridgeProfileConfig): The profile-specific configuration.
            global_config (AniBridgeConfig): The global application configuration.
            shared_animap_client (AniMapClient): The shared AniMap client instance.
        """
        self.profile_name = profile_name
        self.profile_config = profile_config
        self.global_config = global_config
        self.animap_client = shared_animap_client

        self.library_provider: LibraryProvider = build_library_provider(profile_config)
        self.list_provider: ListProvider = build_list_provider(
            profile_name, profile_config
        )

        self.last_synced = self._get_last_synced()
        self.current_sync: SyncProgress | None = None

    async def initialize(self) -> None:
        """Initialize both providers and prepare for synchronization."""
        log.debug(f"[{self.profile_name}] Initializing bridge client")

        await self.library_provider.initialize()
        await self.list_provider.initialize()

        await self.library_provider.clear_cache()
        await self.list_provider.clear_cache()

        await self._backup_list()

        library_user = self.library_provider.user()
        list_user = self.list_provider.user()
        library_label = library_user.title if library_user else "unknown"
        list_label = list_user.title if list_user else "unknown"

        log.info(
            f"[{self.profile_name}] Bridge client initialized for "
            f"library user $$'{library_label}'$$ -> "
            f"list user $$'{list_label}'$$"
        )

    async def close(self) -> None:
        """Close all provider connections."""
        log.debug(f"[{self.profile_name}] Closing bridge client")
        await self.list_provider.close()
        await self.library_provider.close()

    async def refresh_list_provider(self) -> None:
        """Reinitialize the list provider, refreshing any remote state."""
        await self.list_provider.initialize()
        await self.list_provider.clear_cache()

    async def __aenter__(self) -> BridgeClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        await self.close()

    def _get_last_synced_key(self) -> str:
        """Return the database key storing the last sync timestamp."""
        return f"last_synced_{self.profile_name}"

    def _get_last_synced(self) -> datetime | None:
        """Fetch the last successful sync timestamp from the database."""
        with db() as ctx:
            last_synced = ctx.session.get(Housekeeping, self._get_last_synced_key())
            if last_synced is None or last_synced.value is None:
                return None
            return datetime.fromisoformat(last_synced.value)

    def _set_last_synced(self, last_synced: datetime) -> None:
        """Persist the timestamp of the most recent successful sync."""
        self.last_synced = last_synced
        with db() as ctx:
            ctx.session.merge(
                Housekeeping(
                    key=self._get_last_synced_key(), value=last_synced.isoformat()
                )
            )
            ctx.session.commit()

    async def _backup_list(self) -> None:
        """Persist an initial list backup when supported by the provider."""
        try:
            payload = await self.list_provider.backup_list()
        except NotImplementedError:
            return
        except Exception:
            log.error(
                f"[{self.profile_name}] Failed to export list backup",
                exc_info=True,
            )
            return

        if not payload:
            log.debug(
                f"[{self.profile_name}] List provider produced an empty backup; "
                "skipping write"
            )
            return

        target_fname = (
            f"anibridge_{self.profile_name}_{self.list_provider.NAMESPACE}_"
            f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
        )
        target_path = (
            self.profile_config.data_path / "backups" / self.profile_name / target_fname
        )

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(payload, encoding="utf-8")
        except Exception:
            log.error(
                f"[{self.profile_name}] Failed to write backup file to "
                f"$$'{target_path}'$$",
                exc_info=True,
            )
            return

        log.info(
            f"[{self.profile_name}] List provider backup written to $$'{target_path}'$$"
        )

    async def sync(
        self, poll: bool = False, library_keys: Sequence[str] | None = None
    ) -> None:
        """Run a synchronization cycle for the configured profile.

        Args:
            poll (bool): Whether to poll for updates.
            library_keys (Sequence[str] | None): Sequence of library media keys to
                restrict the sync scope.
        """
        library_user = self.library_provider.user()
        list_user = self.list_provider.user()
        library_label = library_user.title if library_user else "unknown"
        list_label = list_user.title if list_user else "unknown"

        log.info(
            f"[{self.profile_name}] Starting "
            f"{'full ' if self.profile_config.full_scan else 'partial '}"
            f"{'and destructive ' if self.profile_config.destructive_sync else ''}"
            f"sync for library user $$'{library_label}'$$ "
            f"-> list user $$'{list_label}'$$"
        )

        sync_start_time = datetime.now(UTC)

        movie_sync = MovieSyncClient(
            library_provider=self.library_provider,
            list_provider=self.list_provider,
            animap_client=self.animap_client,
            excluded_sync_fields=self.profile_config.excluded_sync_fields,
            full_scan=self.profile_config.full_scan,
            destructive_sync=self.profile_config.destructive_sync,
            search_fallback_threshold=self.profile_config.search_fallback_threshold,
            batch_requests=self.profile_config.batch_requests,
            dry_run=self.profile_config.dry_run,
            profile_name=self.profile_name,
        )
        show_sync = ShowSyncClient(
            library_provider=self.library_provider,
            list_provider=self.list_provider,
            animap_client=self.animap_client,
            excluded_sync_fields=self.profile_config.excluded_sync_fields,
            full_scan=self.profile_config.full_scan,
            destructive_sync=self.profile_config.destructive_sync,
            search_fallback_threshold=self.profile_config.search_fallback_threshold,
            batch_requests=self.profile_config.batch_requests,
            dry_run=self.profile_config.dry_run,
            profile_name=self.profile_name,
        )

        movie_sync.clear_cache()
        show_sync.clear_cache()

        sections = list(await self.library_provider.get_sections())

        self.current_sync = SyncProgress(
            state="running",
            started_at=sync_start_time,
            section_index=0,
            section_count=len(sections),
            section_title=None,
            stage="initializing",
            section_items_total=0,
            section_items_processed=0,
        )
        sync_stats = SyncStats()

        try:
            for idx, section in enumerate(sections, start=1):
                if self.current_sync is not None:
                    self.current_sync = self.current_sync.model_copy(
                        update={
                            "section_index": idx,
                            "section_title": section.title,
                            "stage": "enumerating",
                            "section_items_total": 0,
                            "section_items_processed": 0,
                        }
                    )

                section_stats = await self._sync_section(
                    section,
                    poll,
                    movie_sync,
                    show_sync,
                    keys=library_keys,
                    section_index=idx,
                    section_count=len(sections),
                )
                sync_stats = sync_stats.combine(section_stats)

            sync_completion_time = datetime.now(UTC)
            duration = sync_completion_time - sync_start_time

            self._set_last_synced(sync_start_time)

            log.info(
                f"[{self.profile_name}] Sync completed: "
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
                    f"[{self.profile_name}] Unprocessed items: "
                    f"{', '.join([repr(item) for item in unprocessed_items])}"
                )

        except Exception as exc:
            end_time = datetime.now(UTC)
            duration = end_time - sync_start_time

            log.error(
                f"[{self.profile_name}] Sync failed after "
                f"{duration.total_seconds():.2f} seconds: {exc}",
                exc_info=True,
            )
            raise
        finally:
            if self.current_sync is not None:
                self.current_sync = self.current_sync.model_copy(
                    update={"stage": "completed", "state": "idle"}
                )

    async def parse_webhook(
        self, request: Request
    ) -> tuple[bool, Sequence[str] | None]:
        """Parse a webhook request and extract relevant library keys.

        Args:
            request (Request): The incoming webhook request.

        Returns:
            tuple[bool, Sequence[str] | None]: A tuple containing a boolean
                indicating whether the webhook is valid and targetting the profile,
                and a sequence of library media keys to sync, or None if not
                applicable.
        """
        return await self.library_provider.parse_webhook(request)

    async def _sync_section(
        self,
        section: LibrarySection,
        poll: bool,
        movie_sync: MovieSyncClient,
        show_sync: ShowSyncClient,
        keys: Sequence[str] | None = None,
        *,
        section_index: int,
        section_count: int,
    ) -> SyncStats:
        """Synchronize a single library section."""
        log.info(f"[{self.profile_name}] Syncing section $$'{section.title}'$$")

        min_last_modified = (self.last_synced or datetime.now(UTC)) - timedelta(
            seconds=15
        )

        items = list(
            await self.library_provider.list_items(
                section,
                min_last_modified=min_last_modified if poll else None,
                require_watched=not self.profile_config.full_scan,
                keys=keys,
            )
        )

        if self.current_sync is not None:
            self.current_sync = self.current_sync.model_copy(
                update={
                    "section_index": section_index,
                    "section_count": section_count,
                    "section_title": section.title,
                    "section_items_total": len(items),
                    "section_items_processed": 0,
                    "stage": (
                        "prefetching"
                        if self.profile_config.batch_requests
                        else "processing"
                    ),
                }
            )

        if self.profile_config.batch_requests and items:
            await self._prefetch_list_entries(items)

        sync_client: BaseSyncClient
        if section.media_kind == MediaKind.MOVIE:
            sync_client = movie_sync
        elif section.media_kind == MediaKind.SHOW:
            sync_client = show_sync
        else:
            log.warning(
                f"[{self.profile_name}] Unsupported section kind "
                f"'{section.media_kind.value}', skipping"
            )
            return SyncStats()

        for item in items:
            try:
                await sync_client.process_media(item)  # type: ignore[arg-type]

                if self.current_sync is not None:
                    self.current_sync = self.current_sync.model_copy(
                        update={
                            "stage": "processing",
                            "section_items_processed": (
                                self.current_sync.section_items_processed + 1
                            ),
                        }
                    )

            except Exception:
                log.error(
                    f"[{self.profile_name}] Failed to sync item $$'{item.title}'$$",
                    exc_info=True,
                )

        if self.profile_config.batch_requests:
            if self.current_sync is not None:
                self.current_sync = self.current_sync.model_copy(
                    update={"stage": "finalizing"}
                )
            await sync_client.batch_sync()

        return sync_client.sync_stats

    async def _prefetch_list_entries(self, items: Sequence[LibraryMedia]) -> None:
        """Prefetch list entries for the provided media items when batching."""
        imdb_ids, tmdb_ids, tvdb_ids = self._collect_external_ids(items)
        if not imdb_ids and not tmdb_ids and not tvdb_ids:
            return

        mappings = list(
            self.animap_client.get_mappings(
                imdb=imdb_ids or None,
                tmdb=tmdb_ids or None,
                tvdb=tvdb_ids or None,
            )
        )
        keys = sorted(
            {
                str(mapping.anilist_id)
                for mapping in mappings
                if mapping.anilist_id is not None
            }
        )
        if not keys:
            return

        log.info(
            f"[{self.profile_name}] Prefetching {len(keys)} entries from list "
            "provider in batch mode (this may take a while)"
        )

        if self.current_sync is not None:
            self.current_sync = self.current_sync.model_copy(
                update={"stage": "prefetching"}
            )

        try:
            await self.list_provider.get_entries_batch(keys)
        except Exception:
            log.error(
                f"[{self.profile_name}] Failed to prefetch list entries",
                exc_info=True,
            )

    def _collect_external_ids(
        self, items: Sequence[LibraryMedia]
    ) -> tuple[list[str], list[int], list[int]]:
        """Collect external identifiers across a set of media items."""
        imdb_ids: set[str] = set()
        tmdb_ids: set[int] = set()
        tvdb_ids: set[int] = set()

        for item in items:
            for external in item.ids():
                self._append_external_id(external, imdb_ids, tmdb_ids, tvdb_ids)

        return sorted(imdb_ids), sorted(tmdb_ids), sorted(tvdb_ids)

    @staticmethod
    def _append_external_id(
        external: ExternalId,
        imdb_ids: set[str],
        tmdb_ids: set[int],
        tvdb_ids: set[int],
    ) -> None:
        """Normalise and append an external identifier to the appropriate set."""
        namespace = external.namespace.lower()
        if namespace == "imdb":
            imdb_ids.add(external.value)
        elif namespace == "tmdb":
            with contextlib.suppress(ValueError):
                tmdb_ids.add(int(external.value))
        elif namespace == "tvdb":
            with contextlib.suppress(ValueError):
                tvdb_ids.add(int(external.value))
