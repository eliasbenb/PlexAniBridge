"""Scheduler Module."""

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from typing import Any

from tzlocal import get_localzone

from src import log
from src.config.settings import PlexAnibridgeConfig
from src.core import AniMapClient, BridgeClient

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
        polling_scan: bool,
        poll_interval: int = 30,
        stop_event: asyncio.Event | None = None,
    ):
        """Initialize a profile scheduler.

        Args:
            profile_name: Name of the profile
            bridge_client: Bridge client for this profile
            sync_interval: Sync interval in seconds (-1 for single run)
            polling_scan: Whether to use polling mode
            poll_interval: Polling interval in seconds
            stop_event: Event to signal shutdown
        """
        self.profile_name = profile_name
        self.bridge_client = bridge_client
        self.sync_interval = sync_interval
        self.polling_scan = polling_scan
        self.poll_interval = poll_interval
        self.stop_event = stop_event or asyncio.Event()

        self._running = False
        self._sync_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None

    async def sync(self, poll: bool = False) -> None:
        """Execute a single synchronization cycle with error handling.

        Args:
            poll: Flag to enable polling-based sync
        """
        async with self._sync_lock:
            try:
                self._current_task = asyncio.create_task(
                    self.bridge_client.sync(poll=poll)
                )
                await self._current_task
            except asyncio.CancelledError:
                if self._current_task and not self._current_task.done():
                    log.info(
                        f"{self.__class__.__name__}: [{self.profile_name}] Cancelling "
                        f"sync task..."
                    )
                    self._current_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._current_task
                raise
            except Exception:
                log.error(
                    f"{self.__class__.__name__}: [{self.profile_name}] Sync error",
                    exc_info=True,
                )
            finally:
                self._current_task = None

    async def start(self) -> None:
        """Start the profile scheduler."""
        if self._running:
            return

        self._running = True

        if self.sync_interval == -1:
            # Single run mode
            log.debug(
                f"{self.__class__.__name__}: [{self.profile_name}] Running in"
                f"single-run mode"
            )
            await self.sync()
        elif self.polling_scan:
            # Polling mode
            log.debug(
                f"{self.__class__.__name__}: [{self.profile_name}] Starting polling "
                f"mode"
            )
            asyncio.create_task(self._poll_loop())
        else:
            # Periodic mode
            log.debug(
                f"{self.__class__.__name__}: [{self.profile_name}] Starting periodic "
                f"mode"
            )
            asyncio.create_task(self._periodic_loop())

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

                next_sync = datetime.now(timezone.utc) + timedelta(
                    seconds=self.sync_interval
                )
                log.info(
                    f"{self.__class__.__name__}: [{self.profile_name}] Next periodic "
                    f"sync scheduled for: {next_sync.astimezone(get_localzone())}"
                )

                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self.stop_event.wait(), self.sync_interval)
            except asyncio.CancelledError:
                log.debug(
                    f"{self.__class__.__name__}: [{self.profile_name}] Periodic sync "
                    f"cancelled"
                )
                break
            except Exception:
                log.error(
                    f"{self.__class__.__name__}: [{self.profile_name}] Periodic sync "
                    f"error",
                    exc_info=True,
                )
                await asyncio.sleep(10)

    async def _poll_loop(self) -> None:
        """Handle polling-based synchronization."""
        while self._running and not self.stop_event.is_set():
            try:
                await self.sync(poll=True)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                log.info(
                    f"{self.__class__.__name__}: [{self.profile_name}] Poll sync "
                    f"cancelled"
                )
                break
            except Exception:
                log.error(
                    f"{self.__class__.__name__}: [{self.profile_name}] Poll sync error",
                    exc_info=True,
                )
                await asyncio.sleep(10)


class SchedulerClient:
    """Application scheduler that manages all profiles and global tasks.

    Coordinates multiple profile schedulers and handles shared resources like
    the daily database sync. Provides centralized management and graceful shutdown.
    """

    def __init__(self, global_config: PlexAnibridgeConfig):
        """Initialize the application scheduler.

        Args:
            global_config: Global application configuration
        """
        self.global_config = global_config
        self.shared_animap_client = AniMapClient(global_config.data_path)
        self.bridge_clients: dict[str, BridgeClient] = {}
        self.profile_schedulers: dict[str, ProfileScheduler] = {}
        self.stop_event = asyncio.Event()
        self._running = False
        self._daily_sync_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Initialize the application scheduler and all components."""
        log.info(f"{self.__class__.__name__}: Initializing application scheduler")

        log.info(f"{self.__class__.__name__}: Initializing anime mapping database")
        await self.shared_animap_client.initialize()
        log.success(f"{self.__class__.__name__}: Anime mapping database ready")

        for profile_name, profile_config in self.global_config.profiles.items():
            log.info(
                f"{self.__class__.__name__}: [{profile_name}] Setting up bridge client"
            )

            bridge_client = BridgeClient(
                profile_name=profile_name,
                profile_config=profile_config,
                global_config=self.global_config,
                shared_animap_client=self.shared_animap_client,
            )

            await bridge_client.initialize()
            self.bridge_clients[profile_name] = bridge_client

            log.info(f"{self.__class__.__name__}: [{profile_name}] Bridge client ready")

        log.info(
            f"{self.__class__.__name__}: Application scheduler initialized with "
            f"{len(self.bridge_clients)} profile(s)"
        )

    async def start(self) -> None:
        """Start all profile schedulers and global tasks."""
        if self._running:
            return

        self._running = True

        log.info(f"{self.__class__.__name__}: Starting application scheduler")

        self._daily_sync_task = asyncio.create_task(self._daily_db_sync_loop())

        single_run_profiles = []

        for profile_name, bridge_client in self.bridge_clients.items():
            profile_config = self.global_config.get_profile(profile_name)

            log.info(
                f"{self.__class__.__name__}: [{profile_name}] Starting scheduler: "
                f"interval={profile_config.sync_interval}s, "
                f"polling={'enabled' if profile_config.polling_scan else 'disabled'}, "
                f"full_scan={'enabled' if profile_config.full_scan else 'disabled'}, "
                f"destructive={
                    'enabled' if profile_config.destructive_sync else 'disabled'
                }"
            )

            scheduler = ProfileScheduler(
                profile_name=profile_name,
                bridge_client=bridge_client,
                sync_interval=profile_config.sync_interval,
                polling_scan=profile_config.polling_scan,
                poll_interval=30,
                stop_event=self.stop_event,
            )

            self.profile_schedulers[profile_name] = scheduler
            await scheduler.start()

            if profile_config.sync_interval == -1:
                single_run_profiles.append(profile_name)
            else:
                next_sync_time = "in progress"
                if profile_config.sync_interval > 0:
                    next_sync = datetime.now(timezone.utc).astimezone(get_localzone())
                    next_sync_time = f"at {next_sync.strftime('%Y-%m-%d %H:%M:%S')}"

                log.info(
                    f"{self.__class__.__name__}: [{profile_name}] Scheduler started, "
                    f"next sync: {next_sync_time}"
                )

        if single_run_profiles:
            log.info(
                f"{self.__class__.__name__}: Single-run profiles completed: "
                f"{single_run_profiles}"
            )
            # If all profiles are single-run, wait for them to complete and then stop
            if len(single_run_profiles) == len(self.profile_schedulers):
                log.info(
                    f"{self.__class__.__name__}: All profiles are single-run mode, "
                    f"waiting for completion before stopping application"
                )
                # Wait a bit for any final tasks to complete
                await asyncio.sleep(1)
                self.stop_event.set()

        if self.profile_schedulers:
            log.info(
                f"{self.__class__.__name__}: Application scheduler started with "
                f"{len(self.profile_schedulers)} profile(s)"
            )
        else:
            log.warning(
                f"{self.__class__.__name__}: No profile schedulers were started"
            )

    async def stop(self) -> None:
        """Stop all schedulers and clean up resources."""
        if not self._running:
            return

        self._running = False

        log.info(f"{self.__class__.__name__}: Stopping application scheduler")

        self.stop_event.set()

        if self._daily_sync_task and not self._daily_sync_task.done():
            self._daily_sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._daily_sync_task

        stop_tasks = []
        for profile_name, scheduler in self.profile_schedulers.items():
            log.debug(f"{self.__class__.__name__}: [{profile_name}] Stopping scheduler")
            stop_tasks.append(scheduler.stop())

        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        close_tasks = []
        for profile_name, bridge_client in self.bridge_clients.items():
            log.debug(
                f"{self.__class__.__name__}: [{profile_name}] Closing bridge client"
            )
            close_tasks.append(bridge_client.close())

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        await self.shared_animap_client.close()

        self.profile_schedulers.clear()
        self.bridge_clients.clear()

        log.info(f"{self.__class__.__name__}: Application scheduler stopped")

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
        self, profile_name: str | None = None, poll: bool = False
    ) -> None:
        """Manually trigger a sync for one or all profiles.

        Args:
            profile_name: Specific profile to sync, or None for all profiles
            poll: Whether to use polling mode for the sync

        Raises:
            KeyError: If the specified profile doesn't exist
        """
        if profile_name is not None:
            if profile_name not in self.bridge_clients:
                raise KeyError(f"Profile '{profile_name}' not found")

            log.info(
                f"{self.__class__.__name__}: [{profile_name}] Manually triggering sync "
                f"(poll={poll})"
            )
            scheduler = self.profile_schedulers[profile_name]
            await scheduler.sync(poll=poll)
        else:
            log.info(
                f"{self.__class__.__name__}: Manually triggering sync for all profiles "
                f"(poll={poll})"
            )
            sync_tasks = []
            for name, scheduler in self.profile_schedulers.items():
                log.info(f"{self.__class__.__name__}: [{name}] Triggering sync")
                sync_tasks.append(scheduler.sync(poll=poll))

            if sync_tasks:
                await asyncio.gather(*sync_tasks, return_exceptions=True)

    async def get_status(self) -> dict[str, dict[str, Any]]:
        """Get the status of all profiles.

        Returns:
            dict: Status information for each profile
        """
        status = {}

        for profile_name in self.bridge_clients:
            profile_config = self.global_config.get_profile(profile_name)
            bridge_client = self.bridge_clients.get(profile_name)
            scheduler = self.profile_schedulers.get(profile_name)

            status[profile_name] = {
                "config": {
                    "plex_user": profile_config.plex_user,
                    "anilist_user": bridge_client.anilist_client.user.name
                    if bridge_client
                    else "Unknown",
                    "sync_interval": profile_config.sync_interval,
                    "polling_scan": profile_config.polling_scan,
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
        # Start with next day at 1:00 AM UTC
        next_sync_naive = (now + timedelta(days=1)).replace(
            hour=1, minute=0, second=0, microsecond=0
        )

        # If we're already past 1:00 AM today, use today
        today_1am = now.replace(hour=1, minute=0, second=0, microsecond=0)
        if now < today_1am:
            next_sync_naive = today_1am

        return next_sync_naive

    async def _daily_db_sync_loop(self) -> None:
        """Handle daily database synchronization at 1:00 AM UTC."""
        log.info(f"{self.__class__.__name__}: Starting daily database sync scheduler")

        while self._running and not self.stop_event.is_set():
            try:
                now = datetime.now(timezone.utc)
                next_sync_time = self._get_next_1am_utc(now)

                sleep_duration = (next_sync_time - now).total_seconds()

                log.info(
                    f"{self.__class__.__name__}: Next database sync scheduled for: "
                    f"{next_sync_time.astimezone(get_localzone())} "
                    f"(in {sleep_duration / 3600:.1f} hours)"
                )

                try:
                    await asyncio.wait_for(self.stop_event.wait(), sleep_duration)
                    break
                except asyncio.TimeoutError:
                    pass

                if not self._running or self.stop_event.is_set():
                    break

                log.info(f"{self.__class__.__name__}: Starting daily database sync")
                try:
                    await self.shared_animap_client._sync_db()
                    log.success(
                        f"{self.__class__.__name__}: Daily database sync completed"
                    )
                except Exception as e:
                    log.error(
                        f"{self.__class__.__name__}: Daily database sync failed: {e}",
                        exc_info=True,
                    )

            except asyncio.CancelledError:
                log.debug(f"{self.__class__.__name__}: Daily database sync cancelled")
                break
            except Exception:
                log.error(
                    f"{self.__class__.__name__}: Daily database sync error",
                    exc_info=True,
                )
                await asyncio.sleep(3600)  # Retry after 1 hour on error

        log.info("Daily database sync scheduler stopped")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
