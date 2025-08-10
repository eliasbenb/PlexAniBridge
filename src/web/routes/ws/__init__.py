"""Websocket routes."""

from fastapi import APIRouter

from src.web.routes.ws.history import router as history_router
from src.web.routes.ws.logs import router as logs_router
from src.web.routes.ws.status import router as status_router

__all__ = ["router"]

router = APIRouter()

router.include_router(history_router, prefix="/history", tags=["history"])
router.include_router(logs_router, prefix="/logs", tags=["logs"])
router.include_router(status_router, prefix="/status", tags=["status"])
