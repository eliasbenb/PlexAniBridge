"""Websocket log broadcasting handler."""

import asyncio
import logging
import threading
from functools import lru_cache
from typing import Any

from starlette.websockets import WebSocket

from src import log

__all__ = ["WebsocketLogHandler", "get_log_ws_handler"]


class WebsocketLogHandler(logging.Handler):
    """Logging handler that broadcasts log records to active websocket clients."""

    def __init__(self) -> None:
        """Initialize the WebsocketLogHandler."""
        super().__init__()
        self._connections: set[WebSocket] = set()
        self._lock = threading.RLock()
        self._tasks: set[asyncio.Task[Any]] = set()  # Prevents early GC
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the main event loop to schedule tasks from other threads.

        Args:
            loop: The application's main asyncio event loop.
        """
        self._loop = loop

    async def add(self, ws: WebSocket) -> None:
        """Add a websocket connection to the handler.

        Args:
            ws (WebSocket): The websocket connection to add.
        """
        with self._lock:
            self._connections.add(ws)
        log.debug(f"Client added ({len(self._connections)} total)")

    async def remove(self, ws: WebSocket) -> None:
        """Remove a websocket connection from the handler.

        Args:
            ws (WebSocket): The websocket connection to remove.
        """
        with self._lock:
            self._connections.discard(ws)
        log.debug(f"Client removed ({len(self._connections)} total)")

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to all connected websocket clients.

        Args:
            record (logging.LogRecord): The log record to emit.
        """
        try:
            msg = self.format(record)
        except Exception:
            return

        with self._lock:
            conns = list(self._connections)

        if not conns:
            return

        try:
            current_loop = asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            current_loop = None
            in_loop = False

        if in_loop and current_loop is not None:
            for ws in conns:
                task = current_loop.create_task(
                    self._safe_send(ws, msg, record.levelname)
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            return

        if self._loop and not self._loop.is_closed():
            for ws in conns:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._safe_send(ws, msg, record.levelname), self._loop
                    )
                except Exception:
                    continue
            return

    async def _safe_send(self, ws: WebSocket, msg: str, level: str) -> None:
        """Send a message to a websocket connection.

        Args:
            ws (WebSocket): The websocket connection to send the message to.
            msg (str): The message to send.
            level (str): The log level of the message.
        """
        try:
            await ws.send_json({"level": level, "message": msg})
        except Exception:
            await self.remove(ws)


@lru_cache(maxsize=1)
def get_log_ws_handler() -> WebsocketLogHandler:
    """Get the singleton WebsocketLogHandler instance.

    Returns:
        WebsocketLogHandler: The singleton WebsocketLogHandler instance.
    """
    return WebsocketLogHandler()
