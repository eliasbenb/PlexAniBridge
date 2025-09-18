"""API status endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from src.web.state import get_app_state

__all__ = ["router"]


class ProfileConfigModel(BaseModel):
    plex_user: str | None = None
    anilist_user: str | None = None
    sync_interval: int | None = None
    sync_modes: list[str] = []
    full_scan: bool | None = None
    destructive_sync: bool | None = None


class ProfileRuntimeStatusModel(BaseModel):
    running: bool
    last_synced: str | None = None


class ProfileStatusModel(BaseModel):
    config: ProfileConfigModel
    status: ProfileRuntimeStatusModel


class StatusResponse(BaseModel):
    profiles: dict[str, ProfileStatusModel]


router = APIRouter()


@router.get("", response_model=StatusResponse)
async def status() -> StatusResponse:
    """Get the status of the application.

    Returns:
        dict[str, Any]: The status of the application.
    """
    scheduler = get_app_state().scheduler
    if not scheduler:
        return StatusResponse(profiles={})
    raw = await scheduler.get_status()
    converted: dict[str, ProfileStatusModel] = {}
    for name, data in raw.items():
        cfg = data.get("config", {})
        st = data.get("status", {})
        converted[name] = ProfileStatusModel(
            config=ProfileConfigModel(**cfg),
            status=ProfileRuntimeStatusModel(**st),
        )
    return StatusResponse(profiles=converted)
