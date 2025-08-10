"""Route aggregators for the web application."""

from fastapi import APIRouter

from src.web.routes.api import router as api_router  # isort:skip
from src.web.routes.webhook import router as webhook_router  # isort:skip
from src.web.routes.ws import router as ws_router  # isort:skip

from src.web.routes.dashboard import router as dashboard_router
from src.web.routes.logs import router as logs_router
from src.web.routes.mappings import router as mappings_router
from src.web.routes.system import router as system_router

__all__ = ["router"]

router = APIRouter()
page_router = APIRouter()

page_router.include_router(dashboard_router, tags=["dashboard"])
page_router.include_router(logs_router, tags=["logs"])
page_router.include_router(mappings_router, tags=["mappings"])
page_router.include_router(system_router, tags=["system"])

router.include_router(api_router, prefix="/api", tags=["api"])
router.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
router.include_router(ws_router, prefix="/ws", tags=["ws"])
router.include_router(page_router, tags=["pages"])
