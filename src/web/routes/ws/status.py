"""WebSocket routes for live status updates."""

import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient
from src.web.dependencies import get_config_ws, get_scheduler_ws

router = APIRouter()

# Store active WebSocket connections
active_connections: set[WebSocket] = set()


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self) -> None:
        """Initialize the connection manager."""
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept a WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        message_str = json.dumps(message)
        disconnected = set()

        for connection in self.active_connections:
            try:
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_text(message_str)
                else:
                    disconnected.add(connection)
            except Exception:
                disconnected.add(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.active_connections.discard(connection)


manager = ConnectionManager()


@router.websocket("/")
async def websocket_status(
    websocket: WebSocket,
    config: PlexAnibridgeConfig = Depends(get_config_ws),
    scheduler: SchedulerClient = Depends(get_scheduler_ws),
):
    """WebSocket endpoint for real-time status updates."""
    await manager.connect(websocket)

    try:
        # Send initial status
        try:
            status_data = await scheduler.get_status()
        except Exception:
            status_data = {}

        initial_message = {
            "type": "status_update",
            "data": {
                "scheduler_running": scheduler._running if scheduler else False,
                "profiles": status_data,
            },
        }
        await websocket.send_text(json.dumps(initial_message))

        # Keep connection alive and send periodic updates
        while True:
            try:
                # Wait for client message or timeout
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send periodic status update
                try:
                    status_data = await scheduler.get_status()
                    message = {
                        "type": "status_update",
                        "data": {
                            "scheduler_running": scheduler._running
                            if scheduler
                            else False,
                            "profiles": status_data,
                        },
                    }
                    await websocket.send_text(json.dumps(message))
                except Exception:
                    break
            except Exception:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Log the error but don't crash
        print(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)


async def broadcast_status_update(scheduler: SchedulerClient):
    """Broadcast status update to all connected clients."""
    if not manager.active_connections:
        return

    try:
        status_data = await scheduler.get_status()
        message = {
            "type": "status_update",
            "data": {
                "scheduler_running": scheduler._running if scheduler else False,
                "profiles": status_data,
            },
        }
        await manager.broadcast(message)
    except Exception:
        pass


async def broadcast_sync_event(
    profile_name: str, event_type: str, data: dict | None = None
):
    """Broadcast sync event to all connected clients."""
    if not manager.active_connections:
        return

    message = {
        "type": "sync_event",
        "profile_name": profile_name,
        "event_type": event_type,
        "data": data or {},
    }
    await manager.broadcast(message)
