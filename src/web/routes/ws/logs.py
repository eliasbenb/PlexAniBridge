"""Websocket endpoint for live logs."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.web.services.logging_handler import log_ws_handler

router = APIRouter()


@router.websocket("")
async def logs_ws(ws: WebSocket) -> None:
    """Websocket endpoint for live logs.

    Args:
        ws (WebSocket): The WebSocket connection instance.
    """
    await ws.accept()
    await log_ws_handler.add(ws)
    try:
        while True:
            # Keep connection alive; we don't expect client messages
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await log_ws_handler.remove(ws)
