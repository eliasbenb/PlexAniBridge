import sched
import time

from src import log
from src.core import BridgeClient
from src.settings import config


def run() -> None:
    """The main sync loop function"""
    bridge = BridgeClient(
        # General
        partial_scan=config.PARTIAL_SCAN,
        destructive_sync=config.DESTRUCTIVE_SYNC,
        # AniList
        anilist_token=config.ANILIST_TOKEN,
        # Plex
        plex_url=config.PLEX_URL,
        plex_token=config.PLEX_TOKEN,
        plex_sections=config.PLEX_SECTIONS,
        # Advanced
        dry_run=config.DRY_RUN,
        fuzzy_search_threshold=config.FUZZY_SEARCH_THRESHOLD,
    )

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
