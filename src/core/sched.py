import asyncio
import signal
from datetime import datetime, timedelta
from functools import partial

from src import log
from src.core import BridgeClient


class SchedulerClient:
    def __init__(
        self,
        bridge: BridgeClient,
        sync_interval: int,
        polling_scan: bool,
        poll_interval: int = 30,
    ):
        self.bridge = bridge
        self.sync_interval = sync_interval
        self.polling_scan = polling_scan
        self.poll_interval = poll_interval
        self.reinit_interval = sync_interval

        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._sync_lock = asyncio.Lock()
        self._current_task = None
        self.stop_event = asyncio.Event()

    async def run_sync(self, poll: bool) -> None:
        """Function to run a sync job

        Args:
            poll (bool): Flag to enable polling-based sync
        """
        try:
            await asyncio.to_thread(self.bridge.sync, poll=poll)
        except Exception as e:
            log.error(
                f"{self.__class__.__name__}: Sync process error: {e}", exc_info=True
            )

    async def sync(self, poll: bool = False) -> None:
        """Execute a single synchronization cycle with error handling

        Args:
            poll (bool, optional): Flag to enable polling-based sync. Defaults to False.
        """
        async with self._sync_lock:
            try:
                self._current_task = asyncio.create_task(self.run_sync(poll))
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
            except Exception as e:
                log.error(f"{self.__class__.__name__}: Sync error: {e}", exc_info=True)

    async def _periodic_sync(self) -> None:
        """Handle periodic synchronization"""
        while self._running:
            try:
                await self.sync()
                next_sync = datetime.now() + timedelta(seconds=self.sync_interval)
                log.info(
                    f"{self.__class__.__name__}: Next periodic sync scheduled for: {next_sync}"
                )
                await asyncio.sleep(self.sync_interval)
            except asyncio.CancelledError:
                log.info(f"{self.__class__.__name__}: Periodic sync cancelled")
                break
            except Exception as e:
                log.error(
                    f"{self.__class__.__name__}: Periodic sync error: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(10)

    async def _poll_sync(self) -> None:
        """Handle polling-based synchronization"""
        while self._running:
            try:
                await self.sync(poll=True)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                log.info(f"{self.__class__.__name__}: Poll sync cancelled")
                break
            except Exception as e:
                log.error(
                    f"{self.__class__.__name__}: Poll sync error: {e}", exc_info=True
                )
                await asyncio.sleep(10)

    async def _reinit(self) -> None:
        """Handle periodic bridge reinitialization"""
        while self._running:
            try:
                await asyncio.to_thread(self.bridge.reinit)
                next_sync = datetime.now() + timedelta(seconds=self.reinit_interval)
                log.info(
                    f"{self.__class__.__name__}: Next reinit scheduled for: {next_sync}"
                )
                await asyncio.sleep(self.reinit_interval)
            except asyncio.CancelledError:
                log.info(f"{self.__class__.__name__}: Reinit task cancelled")
                break
            except Exception as e:
                log.error(
                    f"{self.__class__.__name__}: Reinit error: {e}", exc_info=True
                )
                await asyncio.sleep(10)

    def _create_task(self, coro) -> None:
        """Create and track an asyncio task"""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _handle_signal(self, sig):
        """Handle termination signals"""
        log.info(f"{self.__class__.__name__}: Received signal {sig.name}")
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        exit(0)

    async def start(self) -> None:
        """Start the scheduler"""
        if self._running:
            return

        self._running = True

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, partial(self._handle_signal, sig))

        if self.reinit_interval >= 0:
            log.info(
                f"{self.__class__.__name__}: Starting reinit scheduler (interval: {self.reinit_interval}s)"
            )
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

        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass

        log.info(f"{self.__class__.__name__}: Scheduler stopped")
