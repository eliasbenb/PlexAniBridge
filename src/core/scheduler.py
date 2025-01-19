import sched
import threading
import time
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

        self.reinit_scheduler = sched.scheduler(time.time, time.sleep)
        self.periodic_scheduler = sched.scheduler(time.time, time.sleep)
        self.poll_thread: threading.Thread | None = None

        self._sync_lock = threading.Lock()
        self._running = True

    def run_sync(self, *args, **kwargs) -> None:
        """Executes a single synchronization cycle between Plex and AniList."""
        with self._sync_lock:
            try:
                self.bridge.sync(*args, **kwargs)
            except Exception as e:
                log.error(f"{self.__class__.__name__}: Error during sync", exc_info=e)

    def schedule_periodic_sync(self, scheduler: sched.scheduler) -> None:
        """Manages periodic execution of the sync process at fixed intervals."""
        try:
            self.run_sync()
        except Exception as e:
            log.error(
                f"{self.__class__.__name__}: Error during periodic sync", exc_info=e
            )
        finally:
            if self._running and self.sync_interval >= 0:
                scheduler.enterabs(
                    time.time() + self.sync_interval,
                    1,
                    self.schedule_periodic_sync,
                    (scheduler,),
                )
                next_period = datetime.now() + timedelta(seconds=self.sync_interval)
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

    def schedule_reinit(self, scheduler: sched.scheduler) -> None:
        """Reinitializes the bridge client at fixed intervals."""
        try:
            self.bridge.reinit()
        except Exception as e:
            log.error(f"{self.__class__.__name__}: Error during reinit", exc_info=e)
        finally:
            if self._running:
                scheduler.enterabs(
                    time.time() + self.sync_interval,
                    1,
                    self.schedule_reinit,
                    (scheduler,),
                )

    def start(self) -> None:
        """Starts both scheduling mechanisms."""
        self._running = True

        self.reinit_scheduler.enterabs(
            time.time(),
            1,
            self.schedule_reinit,
            (self.reinit_scheduler,),
        )
        reinit_scheduler_thread = threading.Thread(
            target=self.reinit_scheduler.run,
            name="reinit_scheduler",
            daemon=True,
        )
        reinit_scheduler_thread.start()

        if self.polling_scan:
            self.poll_thread = threading.Thread(
                target=self.run_poll_sync,
                name="poll_scheduler",
                daemon=True,
            )
            self.poll_thread.start()
            log.info(
                f"{self.__class__.__name__}: Started polling scheduler with interval {self.poll_interval}"
            )
        else:
            self.periodic_scheduler.enterabs(
                time.time(),
                1,
                self.schedule_periodic_sync,
                (self.periodic_scheduler,),
            )
            periodic_scheduler_thread = threading.Thread(
                target=self.periodic_scheduler.run,
                name="periodic_scheduler",
                daemon=True,
            )
            periodic_scheduler_thread.start()
            log.info(
                f"{self.__class__.__name__}: Started periodic scheduler with interval {self.sync_interval}"
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
            self.poll_thread.join(timeout=0.25)
            log.info(f"{self.__class__.__name__}: Stopped polling scheduler")
