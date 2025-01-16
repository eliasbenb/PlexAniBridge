import sched
import threading
import time
from datetime import datetime, timedelta

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
            log.error(
                f"{self.__class__.__name__}: Error during periodic sync", exc_info=e
            )
        finally:
            if self._running:
                scheduler.enterabs(
                    time.time() + config.SYNC_INTERVAL,
                    1,
                    self.schedule_periodic_sync,
                    (scheduler,),
                )
                next_period = datetime.now() + timedelta(seconds=config.SYNC_INTERVAL)
                log.info(
                    f"{self.__class__.__name__}: Next periodic sync at {next_period}"
                )

    def run_poll_sync(self) -> None:
        """Polls for changes and syncs when needed."""
        while self._running:
            try:
                self.run_sync(poll=True)
            except Exception as e:
                log.error(
                    f"{self.__class__.__name__}: Error during polling sync", exc_info=e
                )
            time.sleep(self.poll_interval)

    def start(self) -> None:
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
            log.info(
                f"{self.__class__.__name__}: Started periodic scheduler with interval {config.SYNC_INTERVAL}"
            )

        self.poll_thread = threading.Thread(
            target=self.run_poll_sync,
            name="poll_scheduler",
            daemon=True,
        )
        self.poll_thread.start()
        log.info(
            f"{self.__class__.__name__}: Started polling scheduler with interval {self.poll_interval}"
        )

    def stop(self) -> None:
        """Stops both scheduling mechanisms."""
        self._running = False

        if self.periodic_scheduler:
            for event in self.periodic_scheduler.queue:
                self.periodic_scheduler.cancel(event)
            log.info(f"{self.__class__.__name__}: Stopped periodic scheduler")

        if self.poll_thread and self.poll_thread.is_alive():
            # Wait for poll thread to finish
            self.poll_thread.join(timeout=5)
            log.info(f"{self.__class__.__name__}: Stopped polling scheduler")
