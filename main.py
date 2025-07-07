import asyncio
import signal
from contextlib import asynccontextmanager

from src import PLEXANIBDRIGE_HEADER, config, log
from src.core import BridgeClient, SchedulerClient


@asynccontextmanager
async def create_scheduler(
    bridge: BridgeClient, stop_event: asyncio.Event, **scheduler_kwargs
):
    scheduler = SchedulerClient(bridge, stop_event=stop_event, **scheduler_kwargs)
    try:
        await scheduler.start()
        yield scheduler
    finally:
        await scheduler.stop()


async def main():
    log.info(f"\n{PLEXANIBDRIGE_HEADER}")
    log.info(f"PlexAniBridge: [CONFIG] => {config}")

    stop_event = asyncio.Event()

    def shutdown():
        log.info("PlexAniBridge: Shutting down...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown)

    try:
        async with BridgeClient(config) as bridge:
            async with create_scheduler(
                bridge,
                stop_event=stop_event,
                sync_interval=config.SYNC_INTERVAL,
                polling_scan=config.POLLING_SCAN,
                poll_interval=30,
            ) as _:
                await stop_event.wait()

    except asyncio.CancelledError:
        log.info("PlexAniBridge: Main task cancelled")
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)

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
        pass
    finally:
        log.info("PlexAniBridge: Exiting...")
