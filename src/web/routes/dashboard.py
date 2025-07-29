"""Dashboard route."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient
from src.web.dependencies import get_config, get_scheduler, get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    config: PlexAnibridgeConfig = Depends(get_config),
    scheduler: SchedulerClient = Depends(get_scheduler),
):
    """Dashboard page."""
    from src import __version__

    try:
        status_data = await scheduler.get_status()
    except Exception:
        # If scheduler is not available, show empty state
        status_data = {}

    context = {
        "request": request,
        "title": "Dashboard",
        "version": __version__,
        "profiles": status_data,
        "scheduler_running": scheduler._running if scheduler else False,
        "web_enabled": config.web_server_enabled,
    }

    return templates.TemplateResponse("dashboard.html.jinja", context)


@router.get("/status-card", response_class=HTMLResponse)
async def status_card(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    scheduler: SchedulerClient = Depends(get_scheduler),
):
    """HTMX endpoint for status card updates."""
    from src import __version__

    try:
        status_data = await scheduler.get_status()
    except Exception:
        status_data = {}

    context = {
        "request": request,
        "version": __version__,
        "profiles": status_data,
        "scheduler_running": scheduler._running if scheduler else False,
    }

    return templates.TemplateResponse("components/status_card.html.jinja", context)


@router.get("/metrics-card", response_class=HTMLResponse)
async def metrics_card(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
):
    """HTMX endpoint for metrics card updates."""
    from src.web.routes.api.metrics import get_metrics

    try:
        metrics_data = await get_metrics()

        context = {
            "request": request,
            "total_syncs": metrics_data.total_syncs,
            "sync_activity": [
                {"timestamp": p.timestamp, "value": p.value}
                for p in metrics_data.sync_activity
            ],
            "outcome_distribution": metrics_data.outcome_distribution,
        }

        return templates.TemplateResponse("components/metrics_card.html.jinja", context)
    except Exception:
        # Return empty metrics on error
        context = {
            "request": request,
            "total_syncs": 0,
            "sync_activity": [],
            "outcome_distribution": {},
        }
        return templates.TemplateResponse("components/metrics_card.html.jinja", context)
