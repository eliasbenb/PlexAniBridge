import asyncio
from datetime import datetime, timedelta

from src import log
from src.core import BridgeClient


class SchedulerClient:
    def __init__(
        self,
        bridge: BridgeClient,
        sync_interval: int,
        polling_scan: bool,
        poll_interval: int,
    ) -> None:
        self.bridge = bridge
        self.sync_interval = sync_interval
        self.polling_scan = polling_scan
        self.poll_interval = poll_interval

        self._sync_lock = asyncio.Lock()
        self._running = False
        self._tasks: set[asyncio.Task] = set()

    async def run_sync(self, *args, **kwargs) -> None:
        """Executes a single synchronization cycle between Plex and AniList."""
        async with self._sync_lock:
            try:
                self.bridge.sync(*args, **kwargs)
            except Exception as e:
                log.error(f"{self.__class__.__name__}: Error during sync", exc_info=e)

    async def periodic_sync(self) -> None:
        """Manages periodic execution of the sync process at fixed intervals."""
        while self._running:
            try:
                await self.run_sync()
            except Exception as e:
                log.error(
                    f"{self.__class__.__name__}: Error during periodic sync", exc_info=e
                )

            next_period = datetime.now() + timedelta(seconds=self.sync_interval)
            log.info(f"{self.__class__.__name__}: Next periodic sync at {next_period}")
            await asyncio.sleep(self.sync_interval)

    async def poll_sync(self) -> None:
        """Polls for changes and syncs when needed."""
        while self._running:
            start_time = asyncio.get_event_loop().time()

            try:
                await self.run_sync(poll=True)
            except Exception as e:
                log.error(
                    f"{self.__class__.__name__}: Error during polling sync", exc_info=e
                )

            elapsed = asyncio.get_event_loop().time() - start_time
            wait_time = max(0, self.poll_interval - elapsed)
            await asyncio.sleep(wait_time)

    async def reinit_periodic(self) -> None:
        """Reinitializes the bridge client at fixed intervals."""
        while self._running:
            try:
                self.bridge.reinit()
            except Exception as e:
                log.error(f"{self.__class__.__name__}: Error during reinit", exc_info=e)
            await asyncio.sleep(self.sync_interval)

    def start(self) -> None:
        """Starts all scheduling mechanisms."""
        self._running = True
        loop = asyncio.get_event_loop()

        reinit_task = loop.create_task(self.reinit_periodic())
        self._tasks.add(reinit_task)
        reinit_task.add_done_callback(self._tasks.discard)

        if self.polling_scan:
            poll_task = loop.create_task(self.poll_sync())
            self._tasks.add(poll_task)
            poll_task.add_done_callback(self._tasks.discard)
            log.info(
                f"{self.__class__.__name__}: Started polling scheduler with interval {self.poll_interval}"
            )
        else:
            periodic_task = loop.create_task(self.periodic_sync())
            self._tasks.add(periodic_task)
            periodic_task.add_done_callback(self._tasks.discard)
            log.info(
                f"{self.__class__.__name__}: Started periodic scheduler with interval {self.sync_interval}"
            )

    async def stop(self) -> None:
        """Stops all scheduling mechanisms."""
        self._running = False

        if self._tasks:
            for task in self._tasks:
                task.cancel()

            try:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass

            self._tasks.clear()
            log.info(f"{self.__class__.__name__}: Stopped all schedulers")
