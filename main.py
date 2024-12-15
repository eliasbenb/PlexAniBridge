import sched
import time

from src import log
from src.core import BridgeClient
from src.settings import config


def run():
    bridge = BridgeClient(
        # General
        partial_scan=config.PARTIAL_SCAN,
        destructive_sync=config.DESTRUCTIVE_SYNC,
        # Anilist
        anilist_token=config.ANILIST_TOKEN,
        anilist_user=config.ANILIST_USER,
        # Plex
        plex_url=config.PLEX_URL,
        plex_token=config.PLEX_TOKEN,
        plex_sections=config.PLEX_SECTIONS,
        plex_user=config.PLEX_USER,
        # Advanced
        dry_run=config.DRY_RUN,
        fuzzy_search_threshold=config.FUZZY_SEARCH_THRESHOLD,
    )
    bridge.sync()


def schedule_sync(scheduler: sched.scheduler):
    try:
        run()
    except Exception as e:
        log.error("Scheduler: Failed to sync", exc_info=e)
    finally:
        scheduler.enterabs(
            time.time() + config.SYNC_INTERVAL,
            1,
            schedule_sync,
            (scheduler,),
        )
        log.info(f"Scheduler: Next sync in {config.SYNC_INTERVAL} seconds")


if __name__ == "__main__":
    log.info(f"PlexAniBridge: [CONFIG] => {config}")

    if config.SYNC_INTERVAL == -1:
        log.info(
            "Scheduler: `SYNC_INTERVAL` is set to -1, disabling the scheduler. The script will run once and exit."
        )
        run()
    else:
        s = sched.scheduler(time.time, time.sleep)
        s.enterabs(time.time(), 1, schedule_sync, (s,))

        try:
            s.run()
        except KeyboardInterrupt:
            pass
