"""Websocket endpoint for periodic status snapshots."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.web.state import app_state

router = APIRouter()


@router.websocket("")
async def status_ws(ws: WebSocket) -> None:
    """Websocket endpoint for periodic status snapshots.

    Args:
        ws (WebSocket): The WebSocket connection instance.
    """
    await ws.accept()
    try:
        while True:
            scheduler = app_state.scheduler
            data = (
                {"profiles": await scheduler.get_status()}
                if scheduler
                else {"profiles": {}}
            )
            await ws.send_json(data)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
