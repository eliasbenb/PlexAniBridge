"""System related API endpoints (settings dump, about/runtime info)."""

import platform
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src import __git_hash__, __version__
from src.exceptions import PlexAniBridgeError, SchedulerUnavailableError
from src.web.routes.api.status import (
    ProfileConfigModel,
    ProfileRuntimeStatusModel,
    ProfileStatusModel,
)
from src.web.state import get_app_state

__all__ = ["router"]


class SettingsProfileModel(BaseModel):
    name: str
    settings: dict[str, Any]


class SettingsResponse(BaseModel):
    global_config: dict[str, Any]
    profiles: list[SettingsProfileModel]


class AboutInfoModel(BaseModel):
    version: str
    git_hash: str
    python: str
    platform: str
    utc_now: str
    started_at: str | None = None
    uptime_seconds: int | None = None
    uptime: str | None = None


class AboutResponse(BaseModel):
    info: AboutInfoModel
    status: dict[str, ProfileStatusModel]


class MetaResponse(BaseModel):
    version: str
    git_hash: str


router = APIRouter()


@router.get(
    "/settings",
    summary="Return serialized configuration",
    response_model=SettingsResponse,
)
async def api_settings() -> SettingsResponse:
    """Return the current application configuration as JSON.

    Returns:
        dict[str, Any]: The serialized configuration.
    """
    scheduler = get_app_state().scheduler
    if not scheduler:
        return SettingsResponse(global_config={}, profiles=[])

    global_config = scheduler.global_config.model_dump(
        mode="json", exclude={"profiles"}
    )
    profiles = [
        SettingsProfileModel(name=name, settings=pdata.model_dump(mode="json"))
        for name, pdata in scheduler.global_config.profiles.items()
    ]

    return SettingsResponse(global_config=global_config, profiles=profiles)


@router.get(
    "/about",
    summary="Return runtime & scheduler diagnostics",
    response_model=AboutResponse,
)
async def api_about() -> AboutResponse:
    """Get runtime metadata.

    Returns:
        dict[str, Any]: The runtime metadata.

    Raises:
        SchedulerUnavailableError: If scheduler status cannot be retrieved.
        PlexAniBridgeError: Any domain error raised by underlying components.
    """
    scheduler = get_app_state().scheduler
    status: dict[str, Any] = {}

    if scheduler:
        try:
            status = await scheduler.get_status()
        except PlexAniBridgeError:
            raise
        except Exception as e:
            raise SchedulerUnavailableError(
                f"Unable to fetch scheduler status: {e}"
            ) from e

    started_at = get_app_state().started_at
    now = datetime.now(UTC)
    uptime_seconds: int | None = None
    human_uptime: str | None = None

    if started_at:
        delta = now - started_at
        uptime_seconds = int(delta.total_seconds())
        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        parts: list[str] = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        human_uptime = " ".join(parts)

    info = AboutInfoModel(
        version=__version__,
        git_hash=__git_hash__,
        python=platform.python_version(),
        platform=platform.platform(),
        utc_now=now.isoformat(),
        started_at=started_at.isoformat() if started_at else None,
        uptime_seconds=uptime_seconds,
        uptime=human_uptime,
    )

    converted: dict[str, ProfileStatusModel] = {}
    for name, data in status.items():
        cfg = data.get("config", {})
        st = data.get("status", {})
        converted[name] = ProfileStatusModel(
            config=ProfileConfigModel(**cfg),
            status=ProfileRuntimeStatusModel(**st),
        )
    return AboutResponse(info=info, status=converted)


@router.get("/meta", tags=["meta"], response_model=MetaResponse)
async def meta() -> MetaResponse:
    """Application metadata (version, git hash).

    Returns:
        dict[str, str]: The application metadata.
    """
    return MetaResponse(version=__version__, git_hash=__git_hash__)
