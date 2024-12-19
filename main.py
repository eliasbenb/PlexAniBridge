import sched
import time

from src import log
from src.core import BridgeClient
from src.settings import config
from src.utils.header import plexanibridge_header


def run() -> None:
    """The main sync loop function"""
    bridge = BridgeClient(config)
    bridge.sync()


def schedule_sync(scheduler: sched.scheduler) -> None:
    """A wrapper to run the sync function in scheduled intervals

    Args:
        scheduler (sched.scheduler): The scheduler instance
    """
    try:
        run()
    except Exception as e:  # Trap all exceptions to prevent the program from crashing
        log.error("Scheduler: Failed to sync", exc_info=e)
    finally:  # Schedule the next sync
        scheduler.enterabs(
            time.time() + config.SYNC_INTERVAL,
            1,
            schedule_sync,
            (scheduler,),
        )
        log.info(f"Scheduler: Next sync in {config.SYNC_INTERVAL} seconds")


if __name__ == "__main__":
    log.info(f"\n{plexanibridge_header}")
    log.info(f"PlexAniBridge: [CONFIG] => {config}")

    if config.SYNC_INTERVAL == -1:  # Disable the scheduler
        log.info(
            "Scheduler: `SYNC_INTERVAL` is set to -1, disabling the scheduler. The script will run once and exit."
        )
        run()
    else:  # Enable the scheduler
        s = sched.scheduler(time.time, time.sleep)
        s.enterabs(time.time(), 1, schedule_sync, (s,))

        try:
            s.run()
        except KeyboardInterrupt:  # Allows exiting with a keyboard interrupt
            pass
