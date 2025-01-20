import asyncio
import signal
from contextlib import asynccontextmanager

from src import PLEXANIBDRIGE_HEADER, config, log
from src.core import BridgeClient, SchedulerClient


@asynccontextmanager
async def create_scheduler(bridge: BridgeClient, **scheduler_kwargs):
    """Context manager for creating and managing scheduler lifecycle"""
    scheduler = SchedulerClient(bridge, **scheduler_kwargs)
    try:
        await scheduler.start()
        yield scheduler
    finally:
        await scheduler.stop()


async def main():
    """Asynchronous entry point for PlexAniBridge"""
    log.info(f"\n{PLEXANIBDRIGE_HEADER}")
    log.info(f"PlexAniBridge: [CONFIG] => {config}")

    bridge = BridgeClient(config)

    stop_event = asyncio.Event()

    def signal_handler(sig: signal.Signals) -> None:
        """Signal handler for SIGTERM and SIGINT

        Args:
            sig (signal.Signals): Signal object
        """
        log.info(f"Received signal {sig.name}")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        async with create_scheduler(
            bridge,
            sync_interval=config.SYNC_INTERVAL,
            polling_scan=config.POLLING_SCAN,
            poll_interval=30,
        ) as _:
            await stop_event.wait()
    except asyncio.CancelledError:
        log.info("PlexAniBridge: Main task cancelled")
    finally:
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            log.info(f"PlexAniBridge: Cleaning up {len(tasks)} remaining tasks...")
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("PlexAniBridge: Caught KeyboardInterrupt, shutting down...")
    finally:
        log.info("PlexAniBridge: Exiting...")
