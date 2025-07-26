"""FastAPI application for PlexAniBridge web dashboard."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src import __version__
from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient
from src.web.routes import api, dashboard, logs, profiles, ws


def create_app(config: PlexAnibridgeConfig, scheduler: SchedulerClient) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application configuration
        scheduler: Application scheduler client

    Returns:
        FastAPI: Configured FastAPI application
    """
    app = FastAPI(
        title="PlexAniBridge Dashboard",
        description="PlexAniBridge web dashboard.",
        version=__version__,
    )

    # Add session middleware for potential future auth features
    app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here")

    # Store app dependencies
    app.state.config = config
    app.state.scheduler = scheduler

    # Setup templates and static files
    web_dir = Path(__file__).parent
    templates_dir = web_dir / "templates"
    static_dir = web_dir / "static"

    # Mount static files
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Setup Jinja2 templates
    app.state.templates = Jinja2Templates(directory=templates_dir)

    # Include routers
    app.include_router(dashboard.router, prefix="", tags=["dashboard"])
    app.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
    app.include_router(logs.router, prefix="/logs", tags=["logs"])
    app.include_router(api.router, prefix="/api", tags=["api"])
    app.include_router(ws.router, prefix="/ws", tags=["websocket"])

    return app
