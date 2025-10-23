"""Route aggregators for the web application."""

from fastapi.routing import APIRouter

from src.web.routes.api import router as api_router
from src.web.routes.webhook import router as webhook_router
from src.web.routes.ws import router as ws_router

__all__ = ["router"]

router = APIRouter()

router.include_router(api_router, prefix="/api", tags=[])
router.include_router(webhook_router, prefix="/webhook", tags=[])
router.include_router(ws_router, prefix="/ws", tags=[])
