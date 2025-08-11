"""PlexAniBridge Main Application."""

import asyncio
import signal
import sys

import uvicorn
from pydantic import ValidationError

from src import PLEXANIBDRIGE_HEADER, log
from src.config import config
from src.core.sched import SchedulerClient
from src.web.app import create_app


class GracefulShutdownHandler:
    """Handles graceful shutdown on SIGINT and SIGTERM signals."""

    def __init__(self) -> None:
        """Initialize the shutdown handler."""
        self.shutdown_event = asyncio.Event()
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        if sys.platform != "win32":
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._signal_handler, sig)
        else:
            # Windows signal handling
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig_num=None, frame=None):
        """Handle shutdown signals."""
        sig_name = signal.Signals(sig_num).name if sig_num else "UNKNOWN"
        log.info(
            f"PlexAniBridge: Received {sig_name} signal, initiating graceful "
            f"shutdown..."
        )
        self.shutdown_event.set()

    async def wait_for_shutdown(self):
        """Wait for shutdown signal."""
        await self.shutdown_event.wait()


def validate_configuration():
    """Validate the application configuration and display profile information.

    Returns:
        bool: True if configuration is valid, False otherwise
    """
    try:
        profile_count = len(config.profiles)
        profile_names = list(config.profiles.keys())

        if profile_count == 0:
            log.error("PlexAniBridge: No sync profiles configured")
            return False

        for profile_name in profile_names:
            try:
                profile_config = config.get_profile(profile_name)
                log.info(
                    f"PlexAniBridge: Profile $$'{profile_name}'$$: "
                    f"{str(profile_config)}"
                )
            except KeyError as e:
                log.error(f"PlexAniBridge: Profile $$'{profile_name}'$$ not found: {e}")
                return False
            except ValidationError as e:
                log.error(
                    f"PlexAniBridge: Invalid configuration for profile "
                    f"$$'{profile_name}'$$: {e}"
                )
                return False
            except ValueError as e:
                log.error(
                    f"PlexAniBridge: Configuration error for profile "
                    f"$$'{profile_name}'$$: {e}"
                )
                return False
            except (AttributeError, TypeError) as e:
                log.error(
                    f"PlexAniBridge: Configuration structure error for profile "
                    f"$$'{profile_name}'$$: {e}"
                )
                return False

        return True

    except ValidationError as e:
        log.error(f"PlexAniBridge: Global configuration validation failed: {e}")
        return False
    except ValueError as e:
        log.error(f"PlexAniBridge: Configuration value error: {e}")
        return False
    except (OSError, PermissionError) as e:
        log.error(f"PlexAniBridge: File system error during configuration: {e}")
        return False
    except Exception as e:
        log.error(f"PlexAniBridge: Unexpected configuration error: {e}", exc_info=True)
        return False


async def run() -> int:
    """Main application entry point.

    Initializes and runs the application scheduler until shutdown.

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    app_scheduler: SchedulerClient | None = None
    shutdown_handler: GracefulShutdownHandler | None = None
    server_task: asyncio.Task | None = None

    try:
        log.info("\n" + PLEXANIBDRIGE_HEADER)

        if not validate_configuration():
            return 1

        shutdown_handler = GracefulShutdownHandler()

        app_scheduler = SchedulerClient(config)
        await app_scheduler.initialize()
        await app_scheduler.start()

        if config.web_enabled:
            app = create_app(app_scheduler)
            uv_config = uvicorn.Config(
                app,
                host=config.web_host,
                port=config.web_port,
                log_config=None,
                loop="asyncio",
                proxy_headers=True,
                forwarded_allow_ips="*",
            )
            server = uvicorn.Server(uv_config)
            server_task = asyncio.create_task(server.serve())
            log.success(
                "PlexAniBridge: Web UI started at "
                f"\033[92mhttp://{config.web_host}:{config.web_port} "
                "(ctrl+c to stop)\033[0m"
            )

            await shutdown_handler.wait_for_shutdown()
            server.should_exit = True
            await server_task
        else:
            await shutdown_handler.wait_for_shutdown()

    except KeyboardInterrupt:
        log.info("PlexAniBridge: Keyboard interrupt received, shutting down...")
    except ValidationError as e:
        log.error(f"PlexAniBridge: Configuration validation error: {e}")
        return 1
    except ConnectionError as e:
        log.error(f"PlexAniBridge: Connection error: {e}")
        return 1
    except (OSError, PermissionError) as e:
        log.error(f"PlexAniBridge: File system error: {e}")
        return 1
    except asyncio.CancelledError:
        log.info("PlexAniBridge: Application cancelled")
        return 0
    except Exception as e:
        log.error(f"PlexAniBridge: Unexpected application error: {e}", exc_info=True)
        return 1
    finally:
        if app_scheduler:
            log.info("PlexAniBridge: Shutting down application...")
            try:
                await app_scheduler.stop()
                log.success("PlexAniBridge: Application shutdown complete")
            except asyncio.CancelledError:
                log.info("PlexAniBridge: Shutdown cancelled")
                return 1
            except Exception as e:
                log.error(f"PlexAniBridge: Error during shutdown: {e}", exc_info=True)
                return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Initializes the application and runs the main event loop.

    Args:
        argv (list[str] | None): Command-line arguments (unused).

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        log.info("PlexAniBridge: Application interrupted")
        return 0
    except Exception as e:
        log.error(f"PlexAniBridge: Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
