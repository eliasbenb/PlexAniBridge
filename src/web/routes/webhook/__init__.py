"""Webhook route aggregator."""

from fastapi.routing import APIRouter

from .provider import router as provider_router

__all__ = ["router"]

router = APIRouter()
router.include_router(provider_router, prefix="", tags=["plex"])
