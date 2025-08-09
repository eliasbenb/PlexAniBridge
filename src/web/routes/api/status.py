"""API status endpoints."""

from typing import Any

from fastapi import APIRouter

from src.web.state import app_state

__all__ = ["router"]

router = APIRouter()


@router.get("")
async def status() -> dict[str, Any]:
    """Get the status of the application.

    Returns:
        dict[str, Any]: The status of the application.
    """
    scheduler = app_state.scheduler
    if not scheduler:
        return {"profiles": {}}
    return {"profiles": await scheduler.get_status()}
