"""API status endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from src.web.state import get_app_state

__all__ = [
    "ProfileConfigModel",
    "ProfileRuntimeStatusModel",
    "ProfileStatusModel",
    "router",
]


class ProfileConfigModel(BaseModel):
    """Serialized profile configuration exposed to the web UI."""

    plex_user: str | None = None
    anilist_user: str | None = None
    sync_interval: int | None = None
    sync_modes: list[str] = []
    full_scan: bool | None = None
    destructive_sync: bool | None = None


class ProfileRuntimeStatusModel(BaseModel):
    """Runtime status of a profile exposed to the web UI."""

    running: bool
    last_synced: str | None = None
    current_sync: dict | None = None


class ProfileStatusModel(BaseModel):
    """Combined profile configuration and runtime status exposed to the web UI."""

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
