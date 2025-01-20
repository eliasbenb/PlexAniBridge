import asyncio
from datetime import datetime, timedelta

from src import log
from src.core import BridgeClient


class SchedulerClient:
    """Asynchronous scheduler for managing Plex-AniList synchronization"""

    def __init__(
        self,
        bridge: BridgeClient,
        sync_interval: int,
        polling_scan: bool,
        poll_interval: int = 30,
        reinit_interval: int = 3600,
    ):
        self.bridge = bridge
        self.sync_interval = sync_interval
        self.polling_scan = polling_scan
        self.poll_interval = poll_interval
        self.reinit_interval = reinit_interval
        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._sync_lock = asyncio.Lock()

    async def sync(self, poll: bool = False) -> None:
        """Execute a single synchronization cycle with error handling

        Args:
            poll (bool, optional): Flag to enable polling-based sync. Defaults to False.
        """
        async with self._sync_lock:
            try:
                self.bridge.sync(poll=poll)
            except Exception as e:
                log.error(f"Sync error: {e}", exc_info=True)

    async def _periodic_sync(self) -> None:
        """Handle periodic synchronization"""
        while self._running:
            try:
                await self.sync()
                next_sync = datetime.now() + timedelta(seconds=self.sync_interval)
                log.info(f"Next periodic sync scheduled for: {next_sync}")
                await asyncio.sleep(self.sync_interval)
            except Exception as e:
                log.error(f"Periodic sync error: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _poll_sync(self) -> None:
        """Handle polling-based synchronization"""
        while self._running:
            try:
                await self.sync(poll=True)
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                log.error(f"Poll sync error: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _reinit(self) -> None:
        """Handle periodic bridge reinitialization"""
        while self._running:
            try:
                self.bridge.reinit()
                await asyncio.sleep(self.reinit_interval)
            except Exception as e:
                log.error(f"Reinit error: {e}", exc_info=True)
                await asyncio.sleep(10)

    def _create_task(self, coro) -> None:
        """Create and track an asyncio task"""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start(self) -> None:
        """Start the scheduler"""
        if self._running:
            return

        self._running = True

        if self.sync_interval >= 0:
            self._create_task(self._reinit())

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

    async def stop(self) -> None:
        """Stop the scheduler and clean up"""
        self._running = False

        if self._tasks:
            log.info(f"{self.__class__.__name__}: Stopping all scheduler tasks...")
            for task in self._tasks:
                task.cancel()

            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        log.info(f"{self.__class__.__name__}: Scheduler stopped")
