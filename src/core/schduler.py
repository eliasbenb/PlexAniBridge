import sched
import threading
import time

from src import config, log
from src.core import BridgeClient


class SchedulerClient:
    def __init__(self, bridge: BridgeClient, poll_interval: int = 60) -> None:
        self.bridge = bridge
        self.poll_interval = poll_interval
        self.periodic_scheduler = sched.scheduler(time.time, time.sleep)
        self.poll_thread: threading.Thread | None = None
        self.sync_lock = threading.Lock()
        self._running = True

    def run_sync(self, *args, **kwargs) -> None:
        """Executes a single synchronization cycle between Plex and AniList."""
        with self.sync_lock:
            try:
                self.bridge.sync(*args, **kwargs)
            except Exception as e:
                log.error("Sync failed", exc_info=e)

    def schedule_periodic_sync(self, scheduler: sched.scheduler) -> None:
        """Manages periodic execution of the sync process at fixed intervals."""
        try:
            self.bridge.reinit()
            self.run_sync()
        except Exception as e:
            log.error("Periodic Scheduler: Failed to sync", exc_info=e)
        finally:
            if self._running:
                scheduler.enterabs(
                    time.time() + config.SYNC_INTERVAL,
                    1,
                    self.schedule_periodic_sync,
                    (scheduler,),
                )
                log.info(
                    f"Periodic Scheduler: Next sync in {config.SYNC_INTERVAL} seconds"
                )

    def run_poll_sync(self) -> None:
        """Polls for changes and syncs when needed."""
        while self._running:
            try:
                self.run_sync(poll=True)
                log.info(
                    f"{self.__class__.__name__}:  Changes detected, sync completed"
                )
            except Exception as e:
                log.error(
                    f"{self.__class__.__name__}:  Error during polling", exc_info=e
                )
            time.sleep(self.poll_interval)

    def start(self):
        """Starts both scheduling mechanisms."""
        self._running = True

        if config.SYNC_INTERVAL >= 0:
            self.periodic_scheduler.enterabs(
                time.time(),
                1,
                self.schedule_periodic_sync,
                (self.periodic_scheduler,),
            )
            scheduler_thread = threading.Thread(
                target=self.periodic_scheduler.run,
                name="periodic_scheduler",
                daemon=True,
            )
            scheduler_thread.start()
            log.info("Periodic Scheduler: Started")

        self.poll_thread = threading.Thread(
            target=self.run_poll_sync,
            name="poll_scheduler",
            daemon=True,
        )
        self.poll_thread.start()
        log.info(
            f"{self.__class__.__name__}:  Started (interval: {self.poll_interval}s)"
        )

    def stop(self):
        """Stops both scheduling mechanisms."""
        self._running = False

        if self.periodic_scheduler:
            for event in self.periodic_scheduler.queue:
                self.periodic_scheduler.cancel(event)
            log.info("Periodic Scheduler: Stopped")

        if self.poll_thread and self.poll_thread.is_alive():
            # Wait for poll thread to finish
            self.poll_thread.join(timeout=5)
            log.info(f"{self.__class__.__name__}:  Stopped")
