"""Logs page route."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()


@router.get("/logs", name="logs", response_class=HTMLResponse)
async def logs_page(request: Request) -> HTMLResponse:
    """Render the logs page.

    Args:
        request (Request): The HTTP request object.

    Returns:
        HTMLResponse: The rendered logs page.
    """
    templates: Jinja2Templates = request.app.extra["templates"]
    return templates.TemplateResponse("logs.html.jinja", {"request": request})
