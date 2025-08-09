"""FastAPI application factory and setup."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src import __version__, log
from src.core.sched import SchedulerClient
from src.web.routes import router
from src.web.services.logging_handler import log_ws_handler
from src.web.state import app_state

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan context manager.

    Args:
        app (FastAPI): The FastAPI application instance.

    Returns:
        AsyncGenerator: The application lifespan context manager.
    """
    scheduler: SchedulerClient | None = app.extra.get("scheduler")
    if scheduler is None:
        log.info("Web: No scheduler passed; external lifecycle management expected")
    else:
        app_state.set_scheduler(scheduler)
        if not scheduler._running:
            await scheduler.initialize()
            await scheduler.start()
            log.success("Web: Scheduler started for web UI")

    root_logger = log
    if log_ws_handler not in root_logger.handlers:
        root_logger.addHandler(log_ws_handler)
    try:
        yield
    finally:
        await app_state.shutdown()
        if scheduler and scheduler._running:
            await scheduler.stop()


def create_app(scheduler: SchedulerClient | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        scheduler (SchedulerClient | None): The scheduler client instance.

    Returns:
        FastAPI: The created FastAPI application.
    """
    app = FastAPI(title="PlexAniBridge", lifespan=lifespan)

    if scheduler:
        app.extra["scheduler"] = scheduler

    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals.setdefault("version", __version__)
    templates.env.globals.setdefault("now", datetime.now(timezone.utc))

    app.extra["templates"] = templates
    return app


__all__ = ["create_app"]
