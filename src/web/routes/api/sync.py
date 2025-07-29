"""Sync API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient
from src.web.dependencies import get_config, get_scheduler

router = APIRouter()


class SyncRequest(BaseModel):
    """Sync request model."""

    poll: bool = False


class SyncResponse(BaseModel):
    """Sync response model."""

    message: str
    profile_name: str | None = None


@router.post("/trigger", response_model=SyncResponse)
async def trigger_sync_all(
    request: SyncRequest,
    scheduler: SchedulerClient = Depends(get_scheduler),
) -> SyncResponse:
    """Trigger sync for all profiles."""
    try:
        await scheduler.trigger_sync(poll=request.poll)
        return SyncResponse(
            message="Sync triggered for all profiles",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger sync: {str(e)}"
        ) from e


@router.post("/{profile_name}/trigger", response_model=SyncResponse)
async def trigger_sync_profile(
    profile_name: str,
    request: SyncRequest,
    config: PlexAnibridgeConfig = Depends(get_config),
    scheduler: SchedulerClient = Depends(get_scheduler),
) -> SyncResponse:
    """Trigger sync for a specific profile."""
    if profile_name not in config.profiles:
        raise HTTPException(status_code=404, detail="Profile not found")

    try:
        await scheduler.trigger_sync(profile_name=profile_name, poll=request.poll)
        return SyncResponse(
            message=f"Sync triggered for profile {profile_name}",
            profile_name=profile_name,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Profile not found") from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger sync: {str(e)}"
        ) from e
