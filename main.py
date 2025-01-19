import asyncio
import signal

from src import PLEX_ANIBDRIGE_HEADER, config, log
from src.core import BridgeClient, SchedulerClient


async def main():
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

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        log.info("PlexAniBridge: Caught signal, shutting down...")
        stop_event.set()

    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    loop.add_signal_handler(signal.SIGINT, signal_handler)

    try:
        scheduler.start()
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await scheduler.stop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)
        log.info("PlexAniBridge: Exiting...")


if __name__ == "__main__":
    asyncio.run(main())
