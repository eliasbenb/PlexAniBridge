import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Coroutine

from tzlocal import get_localzone

from src import log
from src.core import BridgeClient

__all__ = ["SchedulerClient"]


class SchedulerClient:
    """Manages periodic and polling-based synchronization tasks for the bridge client.

    Handles scheduling of sync operations, reinit tasks, and graceful shutdown.
    Supports both time-based periodic sync and polling-based sync modes.
    """

    def __init__(
        self,
        bridge: BridgeClient,
        sync_interval: int,
        polling_scan: bool,
        poll_interval: int = 30,
        stop_event: asyncio.Event | None = None,
    ):
        """Initialize the scheduler client.

        Args:
            bridge (BridgeClient): The bridge client to synchronize
            sync_interval (int): Interval in seconds between periodic syncs. Use -1 for single run.
            polling_scan (bool): If True, use polling mode instead of periodic sync
            poll_interval (int, optional): Interval in seconds between polls. Defaults to 30.
            stop_event (asyncio.Event | None, optional): Event to signal shutdown. Defaults to None.
        """
        self.bridge = bridge
        self.sync_interval = sync_interval
        self.polling_scan = polling_scan
        self.poll_interval = poll_interval
        self.reinit_interval = sync_interval

        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._sync_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None
        self.stop_event = stop_event or asyncio.Event()

    async def sync(self, poll: bool = False) -> None:
        """Execute a single synchronization cycle with error handling

        Args:
            poll (bool, optional): Flag to enable polling-based sync. Defaults to False.
        """
        async with self._sync_lock:
            try:
                self._current_task = asyncio.create_task(self.bridge.sync(poll=poll))
                await self._current_task

            except asyncio.CancelledError:
                if self._current_task and not self._current_task.done():
                    log.info(f"{self.__class__.__name__}: Cancelling sync task...")
                    self._current_task.cancel()
                    try:
                        await self._current_task
                    except asyncio.CancelledError:
                        pass
                raise
            except Exception:
                log.error(f"{self.__class__.__name__}: Sync error", exc_info=True)

    async def _periodic_sync(self) -> None:
        """Handle periodic synchronization with configurable intervals."""
        while self._running and not self.stop_event.is_set():
            try:
                await self.sync()
                next_sync = datetime.now(timezone.utc) + timedelta(
                    seconds=self.sync_interval
                )
                log.info(
                    f"{self.__class__.__name__}: Next periodic sync scheduled for: {next_sync.astimezone(get_localzone())}"
                )
                try:
                    await asyncio.wait_for(self.stop_event.wait(), self.sync_interval)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                log.debug(f"{self.__class__.__name__}: Periodic sync cancelled")
                break
            except Exception:
                log.error(
                    f"{self.__class__.__name__}: Periodic sync error: ",
                    exc_info=True,
                )
                await asyncio.sleep(10)

    async def _poll_sync(self) -> None:
        """Handle polling-based synchronization for real-time updates."""
        while self._running:
            try:
                await self.sync(poll=True)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                log.info(f"{self.__class__.__name__}: Poll sync cancelled")
                break
            except Exception:
                log.error(f"{self.__class__.__name__}: Poll sync error", exc_info=True)
                await asyncio.sleep(10)

    async def _reinit(self) -> None:
        """Handle periodic bridge reinitialization to refresh connections."""
        while self._running:
            try:
                await self.bridge.initialize()
                next_reinit = datetime.now(timezone.utc) + timedelta(
                    seconds=self.reinit_interval
                )
                log.info(
                    f"{self.__class__.__name__}: Next reinit scheduled for: {next_reinit.astimezone(get_localzone())}"
                )
                await asyncio.sleep(self.reinit_interval)
            except asyncio.CancelledError:
                log.debug(f"{self.__class__.__name__}: Reinit task cancelled")
                break
            except Exception:
                log.error(f"{self.__class__.__name__}: Reinit error", exc_info=True)
                await asyncio.sleep(10)

    def _create_task(self, coro: Coroutine[Any, Any, None]) -> None:
        """Create and track an asyncio task with automatic cleanup.

        Args:
            coro: The coroutine to run as a task
        """
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start(self) -> None:
        """Start the scheduler with appropriate sync mode."""
        if self._running:
            return

        self._running = True

        if self.polling_scan:
            log.info(
                f"{self.__class__.__name__}: Starting polling scheduler (interval: {self.poll_interval}s)"
            )
            self._create_task(self._poll_sync())
        else:
            log.info(
                f"{self.__class__.__name__}: Starting periodic scheduler (interval: {self.sync_interval}s)"
            )
            if self.sync_interval >= 0:
                self._create_task(self._periodic_sync())
            else:
                log.debug(
                    f"{self.__class__.__name__}: SYNC_INTERVAL is -1, running once and exiting"
                )
                await self.sync()
                exit(0)

        if self.reinit_interval >= 0:
            log.info(
                f"{self.__class__.__name__}: Starting reinit scheduler (interval: {self.reinit_interval}s)"
            )
            self._create_task(self._reinit())

    async def stop(self) -> None:
        """Stop the scheduler and clean up all running tasks."""
        self._running = False
        self.stop_event.set()

        if self._tasks:
            log.debug(f"{self.__class__.__name__}: Stopping all scheduler tasks...")
            for task in self._tasks:
                task.cancel()

            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass

        log.info(f"{self.__class__.__name__}: Scheduler stopped")
