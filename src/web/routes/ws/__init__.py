"""Module for WebSocket routes."""

from fastapi import APIRouter

from src.web.routes.ws.status import router as status_router

router = APIRouter()

router.include_router(status_router, prefix="/status")
