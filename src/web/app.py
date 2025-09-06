"""FastAPI application factory and setup."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from src import log
from src.core.sched import SchedulerClient
from src.web.routes import router
from src.web.services.logging_handler import log_ws_handler
from src.web.state import app_state

FRONTEND_BUILD_DIR = Path(__file__).parent.parent.parent / "frontend" / "build"


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

    index_file = FRONTEND_BUILD_DIR / "index.html"
    if not FRONTEND_BUILD_DIR.exists():
        log.warning(
            "Web: Frontend build directory does not exist, no SPA will be served"
        )
        return app
    if not index_file.exists():
        log.error("Web: Frontend index file does not exist, no SPA will be served")
        return app

    app.mount("/", StaticFiles(directory=FRONTEND_BUILD_DIR, html=True), name="spa")

    api_prefixes = ("/api/", "/ws/", "/webhook/")

    @app.exception_handler(StarletteHTTPException)
    async def spa_404_handler(request: Request, exc: StarletteHTTPException):
        if (
            exc.status_code == 404
            and not request.url.path.startswith(api_prefixes)
            and "." not in request.url.path.rsplit("/", 1)[-1]
        ):
            return FileResponse(index_file)
        return await http_exception_handler(request, exc)

    return app


__all__ = ["create_app"]
