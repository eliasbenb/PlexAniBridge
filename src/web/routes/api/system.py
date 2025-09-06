"""System related API endpoints (settings dump, about/runtime info)."""

import platform
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src import __git_hash__, __version__
from src.web.state import app_state

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
    summary="Return sanitized configuration",
    response_model=SettingsResponse,
)
async def api_settings() -> SettingsResponse:
    """Get sanitized configuration.

    Sensitive token-like fields are masked. Private/underscore keys and some
    large raw fields are omitted to keep the payload lean.

    Returns:
        dict[str, Any]: The sanitized configuration.
    """
    scheduler = app_state.scheduler
    if not scheduler:
        return SettingsResponse(global_config={}, profiles=[])

    secret_keys = {"anilist_token", "plex_token"}
    skip_keys = {"raw_profiles"}

    def _sanitize_mapping(d: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for k, v in d.items():
            if k in skip_keys or k.startswith("_"):
                continue

            if k in secret_keys:
                _v = str(v)
                if not _v:
                    cleaned[k] = None
                elif len(_v) > 6:
                    cleaned[k] = _v[:3] + "************************"
                continue

            cleaned[k] = None if v in (None, "") else v

        return cleaned

    raw_dump = scheduler.global_config.model_dump(mode="json")

    global_config = {
        k: v for k, v in _sanitize_mapping(raw_dump).items() if k not in {"profiles"}
    }

    profiles: list[dict[str, Any]] = []
    for name, pdata in raw_dump.get("profiles", {}).items():
        prof = {"name": name, "settings": _sanitize_mapping(pdata)}
        prof["settings"] = dict(sorted(prof["settings"].items(), key=lambda kv: kv[0]))
        profiles.append(prof)

    global_config = dict(sorted(global_config.items(), key=lambda kv: kv[0]))
    profiles.sort(key=lambda p: p["name"])
    return SettingsResponse(
        global_config=global_config,
        profiles=[SettingsProfileModel(**p) for p in profiles],
    )


@router.get(
    "/about",
    summary="Return runtime & scheduler diagnostics",
    response_model=AboutResponse,
)
async def api_about() -> AboutResponse:
    """Get runtime metadata.

    Returns:
        dict[str, Any]: The runtime metadata.
    """
    scheduler = app_state.scheduler
    status: dict[str, Any] = {}

    if scheduler:
        try:
            status = await scheduler.get_status()
        except Exception as e:
            status = {"error": f"Unable to fetch scheduler status: {e}"}

    started_at = app_state.started_at
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
