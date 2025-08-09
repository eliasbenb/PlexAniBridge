"""API routes."""

from fastapi import APIRouter

from src.web.routes.api.history import router as history_router
from src.web.routes.api.mappings import router as mappings_router
from src.web.routes.api.status import router as status_router
from src.web.routes.api.sync import router as sync_router

__all__ = ["router"]

router = APIRouter()

router.include_router(history_router, prefix="/history", tags=["history"])
router.include_router(mappings_router, prefix="/mappings", tags=["mappings"])
router.include_router(status_router, prefix="/status", tags=["status"])
router.include_router(sync_router, prefix="/sync", tags=["sync"])
