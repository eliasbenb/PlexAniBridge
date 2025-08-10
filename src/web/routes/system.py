"""System/utility page routes."""

from __future__ import annotations

import platform
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src import __git_hash__, __version__
from src.web.state import app_state

router = APIRouter()


@router.get("/settings", name="settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Render a read-only view of the loaded configuration.

    Sensitive values (tokens) are masked. Unset/empty values are shown as
    "(unset)". Lists/dicts are rendered verbatim in the template.
    """
    templates: Jinja2Templates = request.app.extra["templates"]
    scheduler = app_state.scheduler

    if not scheduler:
        return templates.TemplateResponse("settings.html.jinja", {"request": request})

    secret_keys = {"anilist_token", "plex_token"}
    skip_keys = {"raw_profiles"}

    def sanitize_mapping(d: dict) -> dict:
        cleaned: dict[str, object] = {}

        for k, v in d.items():
            if k in skip_keys:
                continue
            if k.startswith("_"):
                continue
            if k in secret_keys:
                if v and v not in ("", None):
                    cleaned[k] = "**********"
                else:
                    cleaned[k] = None
                continue

            if v in (None, ""):
                cleaned[k] = None
            else:
                cleaned[k] = v
        return cleaned

    raw_dump = scheduler.global_config.model_dump(mode="json")

    global_config = {
        k: v for k, v in sanitize_mapping(raw_dump).items() if k not in {"profiles"}
    }

    profiles: list[dict[str, object]] = []
    for name, pdata in raw_dump.get("profiles", {}).items():
        profiles.append(
            {
                "name": name,
                "settings": sanitize_mapping(pdata),
            }
        )

    # Sort for stable display
    global_config = dict(sorted(global_config.items(), key=lambda kv: kv[0]))
    profiles.sort(key=lambda p: p["name"])  # type: ignore
    for p in profiles:
        p["settings"] = dict(sorted(p["settings"].items(), key=lambda kv: kv[0]))  # type: ignore

    context = {
        "request": request,
        "global_config": global_config,
        "profiles": profiles,
    }
    return templates.TemplateResponse("settings.html.jinja", context)


@router.get("/about", name="about", response_class=HTMLResponse)
async def about_page(request: Request) -> HTMLResponse:
    """Render about page with runtime diagnostics and scheduler status."""
    templates: Jinja2Templates = request.app.extra["templates"]
    scheduler = app_state.scheduler
    status: dict = {}
    if scheduler:
        try:
            status = await scheduler.get_status()
        except Exception:
            status = {"error": "Unable to fetch scheduler status"}
    started_at = getattr(app_state, "started_at", None)
    now = datetime.now(UTC)
    uptime_seconds: float | None = None
    human_uptime: str | None = None
    if started_at:
        delta = now - started_at
        uptime_seconds = int(delta.total_seconds())
        # Basic human formatting
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
    info = {
        "version": __version__,
        "git_hash": __git_hash__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "utc_now": now.isoformat(),
        "started_at": started_at.isoformat() if started_at else None,
        "uptime_seconds": uptime_seconds,
        "uptime": human_uptime,
    }
    return templates.TemplateResponse(
        "about.html.jinja", {"request": request, "info": info, "status": status}
    )


__all__ = ["router"]
