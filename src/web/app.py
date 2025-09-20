"""FastAPI application factory and setup."""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from io import BytesIO
from logging import DEBUG
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from src import log
from src.core.sched import SchedulerClient
from src.exceptions import PlexAniBridgeError
from src.web.routes import router
from src.web.services.logging_handler import get_log_ws_handler
from src.web.state import get_app_state

FRONTEND_BUILD_DIR = Path(__file__).parent.parent.parent / "frontend" / "build"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all incoming requests and responses."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        request_info = (
            f"{request.method} {request.url.path}"
            f"{f'?{request.url.query}' if request.url.query else ''} "
            f"from {request.client.host if request.client else 'unknown'}"
        )

        # Capture request body without consuming the stream
        body_info = ""
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()

                request._body = body
                request.scope["body"] = BytesIO(body)

                if body:
                    content_type = request.headers.get("content-type", "").lower()
                    if "application/json" in content_type or "text/" in content_type:
                        try:
                            body_str = body.decode("utf-8")
                            if len(body_str) > 1000:
                                body_str = body_str[:1000] + "..."
                            body_info = f" Body: {body_str}"
                        except UnicodeDecodeError:
                            body_info = f" Body: <binary data, {len(body)} bytes>"
                    else:
                        body_info = (
                            f" Body: <{content_type or 'unknown'}, {len(body)} bytes>"
                        )
            except Exception as e:
                body_info = f" Body: <error reading: {e}>"

        full_request_info = request_info + body_info

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            log.debug(
                f"Request: {full_request_info} -> "
                f"Response: {response.status_code} ({process_time:.3f}s)"
            )

            return response
        except Exception:
            process_time = time.time() - start_time
            log.debug(f"Request: {full_request_info} -> Failed ({process_time:.3f}s)")
            raise


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
        get_app_state().set_scheduler(scheduler)
        if not scheduler._running:
            await scheduler.initialize()
            await scheduler.start()
            log.success("Web: Scheduler started for web UI")

    root_logger = log
    log_ws_handler = get_log_ws_handler()
    if log_ws_handler not in root_logger.handlers:
        root_logger.addHandler(log_ws_handler)
    try:
        loop = asyncio.get_running_loop()
        log_ws_handler.set_event_loop(loop)
    except Exception:
        pass
    try:
        yield
    finally:
        await get_app_state().shutdown()
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

    # Add request logging middleware if in debug mode
    if log.level <= DEBUG:
        app.add_middleware(RequestLoggingMiddleware)
        log.debug("Web: Request logging enabled (debug mode)")

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
    async def spa_404_handler(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        """Serve SPA index.html for unknown routes.

        Args:
            request (Request): The incoming HTTP request.
            exc (StarletteHTTPException): The exception instance.

        Returns:
            Response: The response to return.
        """
        if (
            exc.status_code == 404
            and not request.url.path.startswith(api_prefixes)
            and "." not in request.url.path.rsplit("/", 1)[-1]
        ):
            return FileResponse(index_file)
        return await http_exception_handler(request, exc)

    @app.exception_handler(PlexAniBridgeError)
    async def domain_exception_handler(
        request: Request, exc: PlexAniBridgeError
    ) -> JSONResponse:
        """Handle PlexAniBridge errors with structured JSON responses.

        Args:
            request (Request): The incoming HTTP request.
            exc (PlexAniBridgeError): The exception instance.

        Returns:
            JSONResponse: Structured JSON response with error details.
        """
        cls = exc.__class__
        payload = {
            "error": cls.__name__,
            "detail": str(exc) or cls.__doc__ or "",
            "path": request.url.path,
        }
        return JSONResponse(status_code=cls.status_code, content=payload)

    return app


__all__ = ["create_app"]
