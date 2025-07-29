"""FastAPI application for PlexAniBridge web dashboard."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src import __version__
from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient
from src.web.routes import router


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
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Add session middleware for potential future auth features
    app.add_middleware(
        SessionMiddleware,
        secret_key="TODO: make this a env var whenever auth is implemented",
    )

    # Store app dependencies
    app.state.config = config
    app.state.scheduler = scheduler

    # Setup templates and static files
    web_dir = Path(__file__).parent
    templates_dir = web_dir / "templates"
    static_dir = web_dir / "static"

    # Mount static files
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    templates = Jinja2Templates(directory=templates_dir)

    templates.env.filters["tojson"] = lambda obj: json.dumps(obj)
    templates.env.filters["selectattr"] = lambda seq, attr: [
        item for item in seq if getattr(item, attr, None)
    ]

    templates.env.globals["app_version"] = __version__
    templates.env.globals["app_name"] = "PlexAniBridge"

    app.state.templates = templates

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: HTTPException):
        """Handle 404 errors with a custom template."""
        if request.url.path.startswith("/api/"):
            return {"error": "Not found", "status_code": 404}

        context = {
            "request": request,
            "title": "Page Not Found",
            "status_code": 404,
        }
        return templates.TemplateResponse(
            "errors/404.html.jinja", context, status_code=404
        )

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc: Exception):
        """Handle 500 errors with a custom template."""
        if request.url.path.startswith("/api/"):
            return {"error": "Internal server error", "status_code": 500}

        context = {
            "request": request,
            "title": "Server Error",
            "status_code": 500,
        }
        return templates.TemplateResponse(
            "errors/500.html.jinja", context, status_code=500
        )

    @app.get("/health")
    async def health_check():
        """Simple health check endpoint."""
        return {
            "status": "healthy",
            "version": __version__,
            "scheduler_running": scheduler._running,
        }

    app.include_router(router)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        from src import log

        log.info(
            "Web: Web dashboard started successfully at "
            f"http://{config.web_server_host}:{config.web_server_port}"
        )
        yield
        log.info("Web: Web dashboard shutting down...")

    app.router.lifespan_context = lifespan

    return app
