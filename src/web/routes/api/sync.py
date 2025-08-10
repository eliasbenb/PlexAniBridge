"""API endpoints to trigger sync operations."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.web.state import app_state

__all__ = ["router"]

router = APIRouter()


@router.post("")
async def sync_all(poll: bool = Query(False)) -> dict[str, Any]:
    """Trigger a sync for all profiles.

    Args:
        poll (bool): Whether to poll for updates.

    Returns:
        dict[str, Any]: The response containing the sync status.
    """
    scheduler = app_state.scheduler
    if not scheduler:
        raise HTTPException(503, "Scheduler not available")
    await scheduler.trigger_sync(poll=poll)
    return {"ok": True}


@router.post("/{profile}")
async def sync_profile(profile: str, poll: bool = Query(False)) -> dict[str, Any]:
    """Trigger a sync for a specific profile.

    Args:
        profile (str): The profile to sync.
        poll (bool): Whether to poll for updates.

    Returns:
        dict[str, Any]: The response containing the sync status.
    """
    scheduler = app_state.scheduler
    if not scheduler:
        raise HTTPException(503, "Scheduler not available")
    try:
        await scheduler.trigger_sync(profile, poll=poll)
    except KeyError:
        raise HTTPException(404, f"Profile '{profile}' not found") from None
    return {"ok": True}
