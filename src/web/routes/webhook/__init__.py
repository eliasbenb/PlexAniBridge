"""Webhook route aggregator."""

from fastapi import APIRouter

from .plex import router as plex_router

__all__ = ["router"]

router = APIRouter()
router.include_router(plex_router, prefix="/plex", tags=["plex"])
