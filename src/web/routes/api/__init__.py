"""Module for API routes."""

from fastapi import APIRouter

from src.web.routes.api.health import router as health_router
from src.web.routes.api.metrics import router as metrics_router
from src.web.routes.api.profiles import router as profiles_router
from src.web.routes.api.status import router as status_router
from src.web.routes.api.sync import router as sync_router

__all__ = ["router"]

router = APIRouter()

router.include_router(health_router, prefix="/health")
router.include_router(metrics_router, prefix="/metrics")
router.include_router(profiles_router, prefix="/profiles")
router.include_router(status_router, prefix="/status")
router.include_router(sync_router, prefix="/sync")
