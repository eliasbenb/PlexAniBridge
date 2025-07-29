"""Status API routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient
from src.web.dependencies import get_config, get_scheduler

router = APIRouter()


class ProfileStatus(BaseModel):
    """Profile status model."""

    name: str
    plex_user: str
    anilist_user: str
    sync_interval: int
    polling_scan: bool
    full_scan: bool
    destructive_sync: bool
    running: bool
    last_synced: str | None


class StatusResponse(BaseModel):
    """Status response model."""

    scheduler_running: bool
    profiles: list[ProfileStatus]
    total_profiles: int


@router.get("/", response_model=StatusResponse)
async def get_status(
    config: PlexAnibridgeConfig = Depends(get_config),
    scheduler: SchedulerClient = Depends(get_scheduler),
) -> StatusResponse:
    """Get application status."""
    status_data = await scheduler.get_status()

    profiles = []
    for profile_name, profile_data in status_data.items():
        profile_status = ProfileStatus(
            name=profile_name,
            plex_user=profile_data["config"]["plex_user"],
            anilist_user=profile_data["config"]["anilist_user"],
            sync_interval=profile_data["config"]["sync_interval"],
            polling_scan=profile_data["config"]["polling_scan"],
            full_scan=profile_data["config"]["full_scan"],
            destructive_sync=profile_data["config"]["destructive_sync"],
            running=profile_data["status"]["running"],
            last_synced=profile_data["status"]["last_synced"],
        )
        profiles.append(profile_status)

    return StatusResponse(
        scheduler_running=scheduler._running,
        profiles=profiles,
        total_profiles=len(profiles),
    )
