"""FastAPI dependencies for the web interface."""

from fastapi import Request, WebSocket
from fastapi.templating import Jinja2Templates

from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient


def get_templates(request: Request) -> Jinja2Templates:
    """Get the Jinja2 templates instance."""
    return request.app.state.templates


def get_config(request: Request) -> PlexAnibridgeConfig:
    """Get the application configuration from HTTP request."""
    return request.app.state.config


def get_scheduler(request: Request) -> SchedulerClient:
    """Get the scheduler client from HTTP request."""
    return request.app.state.scheduler


def get_config_ws(websocket: WebSocket) -> PlexAnibridgeConfig:
    """Get the application configuration from WebSocket."""
    return websocket.app.state.config


def get_scheduler_ws(websocket: WebSocket) -> SchedulerClient:
    """Get the scheduler client from WebSocket."""
    return websocket.app.state.scheduler


def get_config_universal(
    request_or_ws: Request | WebSocket,
) -> PlexAnibridgeConfig:
    """Get the application configuration (works with both Request and WebSocket)."""
    return request_or_ws.app.state.config


def get_scheduler_universal(
    request_or_ws: Request | WebSocket,
) -> SchedulerClient:
    """Get the scheduler client (works with both Request and WebSocket)."""
    return request_or_ws.app.state.scheduler
