"""Websocket log broadcasting handler."""

import asyncio
import logging
from functools import lru_cache
from typing import Any

from starlette.websockets import WebSocket

__all__ = ["WebsocketLogHandler", "get_log_ws_handler"]


class WebsocketLogHandler(logging.Handler):
    """Logging handler that broadcasts log records to active websocket clients."""

    def __init__(self) -> None:
        """Initialize the WebsocketLogHandler."""
        super().__init__()
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()  # Prevents early GC

    async def add(self, ws: WebSocket) -> None:
        """Add a websocket connection to the handler.

        Args:
            ws (WebSocket): The websocket connection to add.
        """
        async with self._lock:
            self._connections.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        """Remove a websocket connection from the handler.

        Args:
            ws (WebSocket): The websocket connection to remove.
        """
        async with self._lock:
            self._connections.discard(ws)

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to all connected websocket clients.

        Args:
            record (logging.LogRecord): The log record to emit.
        """
        try:
            msg = self.format(record)
        except Exception:
            return
        for ws in list(self._connections):
            task = asyncio.create_task(self._safe_send(ws, msg, record.levelname))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

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
