"""Global web application state utilities.

Holds references to long-lived singletons (scheduler, log broadcaster, etc.) needed by
route handlers and websocket endpoints.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from plexapi.server import PlexServer

from src.core.sched import SchedulerClient

__all__ = ["AppState", "app_state"]


class AppState:
    """Container for global web application state."""

    def __init__(self) -> None:
        """Initialize empty state containers and record process start time."""
        self.plex: PlexServer | None = None
        self.scheduler: SchedulerClient | None = None
        self.on_shutdown_callbacks: list[Callable[[], Any]] = []
        self.started_at: datetime = datetime.now(UTC)

    def set_scheduler(self, scheduler: SchedulerClient) -> None:
        """Set the scheduler client.

        Args:
            scheduler (SchedulerClient): The scheduler client instance to set.
        """
        self.scheduler = scheduler

    def add_shutdown_callback(self, cb: Callable[[], Any]) -> None:
        """Register a shutdown callback executed during app shutdown.

        Args:
            cb (Callable[[], Any]): The callback function to register.
        """
        self.on_shutdown_callbacks.append(cb)

    async def shutdown(self) -> None:
        """Run registered shutdown callbacks (ignore individual errors).

        Args:
            self (AppState): The application state instance.
        """
        for cb in self.on_shutdown_callbacks:
            try:
                res = cb()
                if hasattr(res, "__await__"):
                    await res
            except Exception:
                pass


app_state = AppState()
