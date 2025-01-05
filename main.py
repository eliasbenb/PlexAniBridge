import sched
import time

from src import PLEX_ANIBDRIGE_HEADER, config, log
from src.core import BridgeClient


def run() -> None:
    """Executes a single synchronization cycle between Plex and AniList.

    Creates a new BridgeClient instance with the current configuration
    and initiates the synchronization process. This function represents
    the core synchronization workflow:
    1. Initialize BridgeClient with configuration
    2. Execute the sync process for all configured user pairs

    Note:
        Any exceptions during sync are propagated to the caller
        for proper handling by the scheduler
    """
    bridge = BridgeClient(config)
    bridge.sync()


def schedule_sync(scheduler: sched.scheduler) -> None:
    """Manages periodic execution of the sync process.

    Wraps the run() function with error handling and scheduling logic,
    ensuring continuous operation even if individual sync cycles fail.

    Args:
        scheduler (sched.scheduler): Active scheduler instance for
            managing future sync cycles

    Error Handling:
        - Catches and logs all exceptions to prevent scheduler termination
        - Always schedules next run regardless of current run's success
        - Uses the configured SYNC_INTERVAL for timing

    Flow:
        1. Execute sync cycle with error trapping
        2. Log any failures that occur
        3. Schedule next sync cycle
        4. Log next sync time
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
    """Main entry point for the PlexAniBridge application.
    
    Handles initialization, configuration display, and execution mode selection:
    
    Program Modes:
        Single Run Mode (SYNC_INTERVAL = -1):
            - Executes one sync cycle
            - Exits after completion
        
        Scheduled Mode (SYNC_INTERVAL >= 0):
            - Initializes scheduler
            - Runs sync cycles at configured intervals
            - Continues until interrupted
    
    Flow:
        1. Display application header
        2. Log current configuration
        3. Check SYNC_INTERVAL setting:
           - If -1: Execute single run
           - If >= 0: Initialize scheduler and begin periodic execution
        4. Handle keyboard interrupts for clean shutdown
    
    Error Handling:
        - KeyboardInterrupt: Allows clean exit via Ctrl+C
        - Other exceptions: Handled by schedule_sync()
    
    Note:
        The scheduler uses time.time for timing and time.sleep
        for delay implementation
    """
    log.info(f"\n{PLEX_ANIBDRIGE_HEADER}")
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
