"""FastAPI dependencies for the web interface."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient


def get_templates(request: Request) -> Jinja2Templates:
    """Get the Jinja2 templates instance."""
    return request.app.state.templates


def get_config(request: Request) -> PlexAnibridgeConfig:
    """Get the application configuration."""
    return request.app.state.config


def get_scheduler(request: Request) -> SchedulerClient:
    """Get the scheduler client."""
    return request.app.state.scheduler
