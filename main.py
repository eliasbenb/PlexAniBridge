import time

from src import PLEX_ANIBDRIGE_HEADER, config, log
from src.core import BridgeClient, SchedulerClient


def main():
    """Entry point for PlexAniBridge

    Initializes the application and starts the scheduler.
    """
    log.info(f"\n{PLEX_ANIBDRIGE_HEADER}")
    log.info(f"PlexAniBridge: [CONFIG] => {config}")

    bridge = BridgeClient(config)
    scheduler = SchedulerClient(
        bridge,
        sync_interval=config.SYNC_INTERVAL,
        polling_scan=config.POLLING_SCAN,
        poll_interval=30,
    )

    try:
        if config.SYNC_INTERVAL == -1:
            log.info(
                "PlexAniBridge: SYNC_INTERVAL set to -1, running once and exiting..."
            )
            scheduler.run_sync()
        else:
            scheduler.start()
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        log.info("PlexAniBridge: Caught KeyboardInterrupt, shutting down...")
    finally:
        scheduler.stop()
        log.info("PlexAniBridge: Exiting...")


if __name__ == "__main__":
    main()
