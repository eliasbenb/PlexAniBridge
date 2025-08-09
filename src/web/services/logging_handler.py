"""Websocket log broadcasting handler."""

from __future__ import annotations

import asyncio
import logging

from starlette.websockets import WebSocket

__all__ = ["WebsocketLogHandler", "log_ws_handler"]


class WebsocketLogHandler(logging.Handler):
    """Logging handler that broadcasts log records to active websocket clients."""

    def __init__(self) -> None:
        """Initialize the WebsocketLogHandler."""
        super().__init__()
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

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
            asyncio.create_task(self._safe_send(ws, msg, record.levelname))

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


log_ws_handler = WebsocketLogHandler()
