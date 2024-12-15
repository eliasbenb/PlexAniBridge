import sched
import time

from src import log
from src.core import BridgeClient
from src.settings import config


def schedule_sync(scheduler: sched.scheduler):
    try:
        bridge = BridgeClient(
            dry_run=config.DRY_RUN,
            anilist_token=config.ANILIST_TOKEN,
            anilist_user=config.ANILIST_USER,
            plex_url=config.PLEX_URL,
            plex_token=config.PLEX_TOKEN,
            plex_sections=config.PLEX_SECTIONS,
            plex_user=config.PLEX_USER,
            fuzzy_search_threshold=config.FUZZY_SEARCH_THRESHOLD,
        )
        bridge.sync()
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
    s = sched.scheduler(time.time, time.sleep)
    s.enterabs(time.time(), 1, schedule_sync, (s,))

    try:
        s.run()
    except KeyboardInterrupt:
        pass
