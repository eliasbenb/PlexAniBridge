"""API endpoints to trigger sync operations."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.exceptions import SchedulerNotInitializedError
from src.web.state import get_app_state

__all__ = ["router"]


class OkResponse(BaseModel):
    ok: bool = True


router = APIRouter()


@router.post("", response_model=OkResponse)
async def sync_all(poll: bool = Query(False)) -> OkResponse:
    """Trigger a sync for all profiles.

    Args:
        poll (bool): Whether to poll for updates.

    Returns:
        OkResponse: The response containing the sync status.
    """
    scheduler = get_app_state().scheduler
    if not scheduler:
        raise SchedulerNotInitializedError("Scheduler not available")
    await scheduler.trigger_sync(poll=poll)
    return OkResponse(ok=True)


@router.post("/database", response_model=OkResponse)
async def sync_database() -> OkResponse:
    """Trigger a sync for the database.

    Returns:
        OkResponse: The response containing the sync status.
    """
    scheduler = get_app_state().scheduler
    if not scheduler:
        raise SchedulerNotInitializedError("Scheduler not available")
    await scheduler.shared_animap_client._sync_db()
    return OkResponse(ok=True)


@router.post("/profile/{profile}", response_model=OkResponse)
async def sync_profile(profile: str, poll: bool = Query(False)) -> OkResponse:
    """Trigger a sync for a specific profile.

    Args:
        profile (str): The profile to sync.
        poll (bool): Whether to poll for updates.

    Returns:
        OkResponse: The response containing the sync status.
    """
    scheduler = get_app_state().scheduler
    if not scheduler:
        raise SchedulerNotInitializedError("Scheduler not available")
    await scheduler.trigger_sync(profile, poll=poll)
    return OkResponse(ok=True)
