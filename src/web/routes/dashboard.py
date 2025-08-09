"""Dashboard page routes."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.web.state import app_state

router = APIRouter()


@router.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root() -> str:
    """Redirect to the dashboard.

    Returns:
        str: The URL to redirect to.
    """
    return "/dashboard"


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard page.

    Args:
        request (Request): The HTTP request object.

    Returns:
        HTMLResponse: The rendered dashboard page.
    """
    templates: Jinja2Templates = request.app.extra["templates"]
    scheduler = app_state.scheduler
    status = await scheduler.get_status() if scheduler else {}
    return templates.TemplateResponse(
        "dashboard.html.jinja",
        {"request": request, "status": status},
    )


@router.get("/timeline/{profile}", response_class=HTMLResponse)
async def profile_timeline(request: Request, profile: str) -> HTMLResponse:
    """Render the sync timeline page for a profile."""
    templates: Jinja2Templates = request.app.extra["templates"]
    scheduler = app_state.scheduler
    if scheduler:
        st = await scheduler.get_status()
        if profile not in st:
            raise HTTPException(404, "Profile not found")
    return templates.TemplateResponse(
        "timeline.html.jinja", {"request": request, "profile": profile}
    )
