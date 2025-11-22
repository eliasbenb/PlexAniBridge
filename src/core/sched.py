"""Scheduler Module."""

import asyncio
import contextlib
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from cachetools.func import lru_cache
from tzlocal import get_localzone

from src import log
from src.config.settings import (
    AniBridgeConfig,
    AniBridgeProfileConfig,
    SyncMode,
)
from src.core import AniMapClient, BridgeClient
from src.exceptions import ProfileNotFoundError

__all__ = ["SchedulerClient"]


class ProfileScheduler:
    """Individual profile scheduler for managing sync operations.

    Handles the scheduling logic for a single profile, including periodic
    sync, polling mode, and single-run mode.
    """

    def __init__(
        self,
        profile_name: str,
        bridge_client: BridgeClient,
        sync_interval: int,
        sync_modes: list[SyncMode],
        poll_interval: int = 30,
        stop_event: asyncio.Event | None = None,
    ):
        """Initialize a profile scheduler.

        Args:
            profile_name: Name of the profile
            bridge_client: Bridge client for this profile
            sync_interval: Sync interval in seconds
            sync_modes: List of sync modes enabled for this profile
            poll_interval: Polling interval in seconds
            stop_event: Event to signal shutdown
        """
        self.profile_name = profile_name
        self.bridge_client = bridge_client
        self.sync_interval = sync_interval
        self.sync_modes = sync_modes
        self.poll_interval = poll_interval
        self.stop_event = stop_event or asyncio.Event()

        self._running = False
        self._sync_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()  # Prevents early GC

    async def sync(
        self, poll: bool = False, library_keys: Sequence[str] | None = None
    ) -> None:
        """Execute a single synchronization cycle with error handling.

        Args:
            poll (bool): Flag to enable polling-based sync.
            library_keys (Sequence[str] | None): Sequence of library media keys to
                restrict the sync scope.
        """
        async with self._sync_lock:
            try:
                self._current_task = asyncio.create_task(
                    self.bridge_client.sync(poll=poll, library_keys=library_keys)
                )
                await self._current_task
            except asyncio.CancelledError:
                if self._current_task and not self._current_task.done():
                    log.info(f"[{self.profile_name}] Cancelling sync task...")
                    self._current_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._current_task
                raise
            except Exception:
                log.error(f"[{self.profile_name}] Sync error", exc_info=True)
            finally:
                self._current_task = None

    async def start(self) -> None:
        """Start the profile scheduler."""
        if self._running:
            return

        if not self.sync_modes:
            log.debug(
                f"[{self.profile_name}] No sync modes "
                f"configured, triggering single run before exiting"
            )
            await self.sync()
            return

        self._running = True

        if SyncMode.PERIODIC in self.sync_modes:
            log.debug(
                f"[{self.profile_name}] Starting periodic "
                f"sync every {self.sync_interval}s"
            )
            task = asyncio.create_task(self._periodic_loop())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        if SyncMode.POLL in self.sync_modes:
            log.debug(
                f"[{self.profile_name}] Starting polling "
                f"sync every {self.poll_interval}s"
            )
            task = asyncio.create_task(self._poll_loop())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        """Stop the profile scheduler."""
        self._running = False
        self.stop_event.set()

        current_task = self._current_task
        if current_task and not current_task.done():
            current_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await current_task

    async def _periodic_loop(self) -> None:
        """Handle periodic synchronization."""
        while self._running and not self.stop_event.is_set():
            try:
                await self.sync()

                next_sync = datetime.now(UTC) + timedelta(seconds=self.sync_interval)
                log.info(
                    f"[{self.profile_name}] Next periodic "
                    f"sync scheduled for: {next_sync.astimezone(get_localzone())}"
                )

                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self.stop_event.wait(), self.sync_interval)
            except asyncio.CancelledError:
                log.debug(f"[{self.profile_name}] Periodic sync cancelled")
                break
            except Exception:
                log.error(f"[{self.profile_name}] Periodic sync error", exc_info=True)
                await asyncio.sleep(10)

    async def _poll_loop(self) -> None:
        """Handle polling-based synchronization."""
        while self._running and not self.stop_event.is_set():
            try:
                await self.sync(poll=True)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                log.info(f"[{self.profile_name}] Poll sync cancelled")
                break
            except Exception:
                log.error(f"[{self.profile_name}] Poll sync error", exc_info=True)
                await asyncio.sleep(10)


class SchedulerClient:
    """Application scheduler that manages all profiles and global tasks.

    Coordinates multiple profile schedulers and handles shared resources like
    the daily database sync. Provides centralized management and graceful shutdown.
    """

    def __init__(self, global_config: AniBridgeConfig):
        """Initialize the application scheduler.

        Args:
            global_config (AniBridgeConfig): Global application configuration.
        """
        self.global_config = global_config
        self.shared_animap_client = AniMapClient(
            global_config.data_path, global_config.mappings_url
        )
        self.bridge_clients: dict[str, BridgeClient] = {}
        self.profile_schedulers: dict[str, ProfileScheduler] = {}
        self.stop_event = asyncio.Event()
        self._running = False
        self._daily_sync_task: asyncio.Task | None = None

    def request_shutdown(self) -> None:
        """Request application shutdown from external callers."""
        if not self.stop_event.is_set():
            self.stop_event.set()

    @property
    def is_running(self) -> bool:
        """Return whether the scheduler main loop is currently running."""
        return self._running

    def get_next_database_sync_at(self) -> datetime | None:
        """Return the next scheduled database sync time in UTC."""
        if not self._running:
            return None
        now = datetime.now(UTC)
        return self._get_next_1am_utc(now)

    async def initialize(self) -> None:
        """Initialize the application scheduler and all components."""
        log.info("Initializing application scheduler")

        log.info("Initializing anime mapping database")
        await self.shared_animap_client.initialize()
        log.success("Anime mapping database ready")

        for profile_name, profile_config in self.global_config.profiles.items():
            log.info(f"[{profile_name}] Setting up bridge client")

            bridge_client = BridgeClient(
                profile_name=profile_name,
                profile_config=profile_config,
                global_config=self.global_config,
                shared_animap_client=self.shared_animap_client,
            )

            await bridge_client.initialize()
            self.bridge_clients[profile_name] = bridge_client

            log.info(f"[{profile_name}] Bridge client ready")

        log.info(
            f"Application scheduler initialized with "
            f"{len(self.bridge_clients)} profile(s)"
        )

    async def start(self) -> None:
        """Start all profile schedulers and global tasks."""
        if self._running:
            return

        self._running = True

        log.info("Starting application scheduler")

        self._daily_sync_task = asyncio.create_task(self._daily_db_sync_loop())

        for profile_name, bridge_client in self.bridge_clients.items():
            profile_config = self.global_config.get_profile(profile_name)

            log.info(
                f"[{profile_name}] Starting scheduler: "
                f"interval={profile_config.sync_interval}s, "
                f"modes={profile_config.sync_modes}, "
                f"full_scan={'enabled' if profile_config.full_scan else 'disabled'}, "
                f"destructive={
                    'enabled' if profile_config.destructive_sync else 'disabled'
                }"
            )

            scheduler = ProfileScheduler(
                profile_name=profile_name,
                bridge_client=bridge_client,
                sync_interval=profile_config.sync_interval,
                sync_modes=profile_config.sync_modes,
                poll_interval=30,
                stop_event=self.stop_event,
            )

            self.profile_schedulers[profile_name] = scheduler
            await scheduler.start()

            if profile_config.sync_modes:
                next_sync_time = "in progress"
                if (
                    SyncMode.PERIODIC in profile_config.sync_modes
                    and profile_config.sync_interval > 0
                ):
                    next_sync = datetime.now(UTC).astimezone(get_localzone())
                    next_sync_time = f"at {next_sync.strftime('%Y-%m-%d %H:%M:%S')}"

                log.info(
                    f"[{profile_name}] Scheduler started, next sync: {next_sync_time}"
                )

        # If every profile is a single-run profile (no sync_modes), exit
        if self.profile_schedulers and all(
            not self.global_config.get_profile(name).sync_modes
            for name in self.profile_schedulers
        ):
            log.info("All profiles are single-run, stopping application")
            self.stop_event.set()
            return

        if self.profile_schedulers:
            log.info(
                f"Application scheduler started with "
                f"{len(self.profile_schedulers)} profile(s)"
            )
        else:
            log.warning("No profile schedulers were started")

    async def stop(self) -> None:
        """Stop all schedulers and clean up resources."""
        if not self._running:
            return

        self._running = False

        log.info("Stopping application scheduler")

        self.stop_event.set()

        if self._daily_sync_task and not self._daily_sync_task.done():
            self._daily_sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._daily_sync_task

        stop_tasks = []
        for profile_name, scheduler in self.profile_schedulers.items():
            log.debug(f"[{profile_name}] Stopping scheduler")
            stop_tasks.append(scheduler.stop())

        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        close_tasks = []
        for profile_name, bridge_client in self.bridge_clients.items():
            log.debug(f"[{profile_name}] Closing bridge client")
            close_tasks.append(bridge_client.close())

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        await self.shared_animap_client.close()

        self.profile_schedulers.clear()
        self.bridge_clients.clear()

        log.info("Application scheduler stopped")

    async def wait_for_completion(self) -> None:
        """Wait for the application to complete or be stopped."""
        if not self._running:
            return

        try:
            await self.stop_event.wait()
        except asyncio.CancelledError:
            log.info("Application scheduler wait interrupted")
            raise

    async def trigger_sync(
        self,
        profile_name: str | None = None,
        poll: bool = False,
        library_keys: Sequence[str] | None = None,
    ) -> None:
        """Manually trigger a sync for one or all profiles.

        Args:
            profile_name (str | None): Specific profile to sync, or None for all.
            poll (bool): Whether to use polling mode for the sync.
            library_keys (Sequence[str] | None): Optional list of library media keys to.
                restrict the sync scope for each profile.

        Raises:
            KeyError: If the specified profile doesn't exist
        """
        if profile_name is not None:
            if profile_name not in self.bridge_clients:
                raise ProfileNotFoundError(f"Profile '{profile_name}' not found")

            log.info(f"[{profile_name}] Manually triggering sync (poll={poll})")
            scheduler = self.profile_schedulers[profile_name]
            await scheduler.sync(poll=poll, library_keys=library_keys)
        else:
            log.info(f"Manually triggering sync for all profiles (poll={poll})")
            sync_tasks = []
            for name, scheduler in self.profile_schedulers.items():
                log.info(f"[{name}] Triggering sync")
                sync_tasks.append(scheduler.sync(poll=poll, library_keys=library_keys))

            if sync_tasks:
                await asyncio.gather(*sync_tasks, return_exceptions=True)

    async def get_status(self) -> dict[str, dict[str, Any]]:
        """Get the status of all profiles.

        Returns:
            dict[str, dict[str, Any]]: A dictionary containing the profile info.
        """
        status = {}

        for profile_name in self.bridge_clients:
            profile_config = self.global_config.get_profile(profile_name)
            bridge_client = self.bridge_clients.get(profile_name)
            scheduler = self.profile_schedulers.get(profile_name)

            library_namespace: str | None = None
            list_namespace: str | None = None
            library_user_title: str | None = None
            list_user_title: str | None = None

            if bridge_client is not None:
                library_namespace = bridge_client.library_provider.NAMESPACE.title()
                list_namespace = bridge_client.list_provider.NAMESPACE.title()

                library_user = bridge_client.library_provider.user()
                if library_user is not None:
                    library_user_title = library_user.title

                list_user = bridge_client.list_provider.user()
                if list_user is not None:
                    list_user_title = list_user.title

            status[profile_name] = {
                "config": {
                    "library_namespace": library_namespace,
                    "list_namespace": list_namespace,
                    "library_user": library_user_title,
                    "list_user": list_user_title,
                    "sync_interval": profile_config.sync_interval,
                    "sync_modes": [m.value for m in profile_config.sync_modes],
                    "full_scan": profile_config.full_scan,
                    "destructive_sync": profile_config.destructive_sync,
                },
                "status": {
                    "running": scheduler is not None and scheduler._running
                    if scheduler
                    else False,
                    "last_synced": bridge_client.last_synced.isoformat()
                    if bridge_client and bridge_client.last_synced
                    else None,
                    "current_sync": (
                        bridge_client.current_sync.model_dump(mode="json")
                        if bridge_client and bridge_client.current_sync is not None
                        else None
                    ),
                },
            }

        return status

    def _get_next_1am_utc(self, now: datetime) -> datetime:
        """Calculate the next 1:00 AM UTC, handling DST transitions properly.

        Args:
            now: Current UTC datetime

        Returns:
            datetime: Next 1:00 AM UTC
        """
        candidate = now.replace(hour=1, minute=0, second=0, microsecond=0)
        if now >= candidate:
            candidate += timedelta(days=1)
        return candidate

    async def _daily_db_sync_loop(self) -> None:
        """Handle daily database synchronization at 1:00 AM UTC."""
        log.info("Starting daily database sync scheduler")

        while self._running and not self.stop_event.is_set():
            try:
                now = datetime.now(UTC)
                next_sync_time = self._get_next_1am_utc(now)

                sleep_duration = (next_sync_time - now).total_seconds()

                log.info(
                    f"Next database sync scheduled for: "
                    f"{next_sync_time.astimezone(get_localzone())} "
                    f"(in {sleep_duration / 3600:.1f} hours)"
                )

                try:
                    await asyncio.wait_for(self.stop_event.wait(), sleep_duration)
                    break
                except TimeoutError:
                    pass

                if not self._running or self.stop_event.is_set():
                    break

                log.info("Starting daily database sync")
                try:
                    await self.shared_animap_client.sync_db()
                    log.success("Daily database sync completed")

                    log.info("Reinitializing all list providers")
                    for bridge_client in self.bridge_clients.values():
                        await bridge_client.refresh_list_provider()
                except Exception as e:
                    log.error(f"Daily database sync failed: {e}", exc_info=True)

            except asyncio.CancelledError:
                log.debug("Daily database sync cancelled")
                break
            except Exception:
                log.error("Daily database sync error", exc_info=True)
                await asyncio.sleep(3600)  # Retry after 1 hour on error

        log.info("Daily database sync scheduler stopped")

    @lru_cache(maxsize=128)
    def get_profiles_for_plex_account(
        self, account_id: int | str
    ) -> list[tuple[str, AniBridgeProfileConfig]]:
        """Find all profile names and their configs by Plex account id.

        This is memoized to avoid repeated linear scans of profile lists for
        frequent webhook requests.

        Args:
            account_id (int | str): Plex user account id to search for.

        Returns:
            list[tuple[str, AniBridgeProfileConfig]]: A list of tuples containing
                the profile names and their configurations.

        Raises:
            KeyError: If no profile matches the given account id
        """
        account_key = str(account_id)
        profiles: list[tuple[str, AniBridgeProfileConfig]] = []
        for profile_name, bridge_client in self.bridge_clients.items():
            if bridge_client is None:
                continue

            library_user = bridge_client.library_provider.user()
            if library_user is None:
                continue

            if str(library_user.key) == account_key:
                profile_config = self.global_config.get_profile(profile_name)
                profiles.append((profile_name, profile_config))

        if not profiles:
            raise ProfileNotFoundError(
                f"Profile for Plex account id '{account_key}' not found"
            )

        return profiles

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
