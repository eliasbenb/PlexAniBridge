"""Profile routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select

from src.config.database import db
from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient
from src.models.db.sync_history import SyncHistory
from src.web.dependencies import get_config, get_scheduler, get_templates

router = APIRouter()


@router.get("/{profile_name}", response_class=HTMLResponse)
async def profile_detail(
    profile_name: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    config: PlexAnibridgeConfig = Depends(get_config),
    scheduler: SchedulerClient = Depends(get_scheduler),
):
    """Profile detail page with sync history timeline."""
    if profile_name not in config.profiles:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile_config = config.get_profile(profile_name)

    with db as ctx:
        # Get recent sync history
        query = (
            select(SyncHistory)
            .where(SyncHistory.profile_name == profile_name)
            .order_by(desc(SyncHistory.timestamp))
            .limit(20)
        )

        sync_history = ctx.session.execute(query).scalars().all()

    anilist_user = scheduler.bridge_clients[profile_name].anilist_client.user.name

    context = {
        "request": request,
        "title": f"Profile: {profile_name}",
        "profile_name": profile_name,
        "profile_config": profile_config,
        "anilist_user": anilist_user,
        "sync_history": sync_history,
    }

    return templates.TemplateResponse("profile_detail.html.jinja", context)


@router.get("/{profile_name}/timeline", response_class=HTMLResponse)
async def profile_timeline(
    profile_name: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    config: PlexAnibridgeConfig = Depends(get_config),
):
    """HTMX endpoint for profile timeline updates."""
    if profile_name not in config.profiles:
        raise HTTPException(status_code=404, detail="Profile not found")

    with db as ctx:
        # Get recent sync history
        query = (
            select(SyncHistory)
            .where(SyncHistory.profile_name == profile_name)
            .order_by(desc(SyncHistory.timestamp))
            .limit(50)
        )

        sync_history = ctx.session.execute(query).scalars().all()

    context = {
        "request": request,
        "profile_name": profile_name,
        "sync_history": sync_history,
    }

    return templates.TemplateResponse("components/timeline.html.jinja", context)


@router.get("/{profile_name}/stats", response_class=HTMLResponse)
async def profile_stats(
    profile_name: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    config: PlexAnibridgeConfig = Depends(get_config),
):
    """Get rendered HTML stats for a profile."""
    if profile_name not in config.profiles:
        raise HTTPException(status_code=404, detail="Profile not found")

    with db as ctx:
        query = select(SyncHistory).where(SyncHistory.profile_name == profile_name)
        results = ctx.session.execute(query).scalars().all()

        stats = {
            "total_syncs": len(results),
            "synced": 0,
            "skipped": 0,
            "failed": 0,
            "not_found": 0,
            "deleted": 0,
            "pending": 0,
        }

        for result in results:
            if result.outcome in stats:
                stats[result.outcome] += 1

        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        recent_results = [
            r
            for r in results
            if r.timestamp.replace(tzinfo=timezone.utc) >= recent_cutoff
        ]
        stats["recent_activity"] = len(recent_results)

    context = {
        "request": request,
        "profile_name": profile_name,
        **stats,
    }

    return templates.TemplateResponse("components/profile_stats.html.jinja", context)
