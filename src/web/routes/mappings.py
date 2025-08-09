"""Mappings editor page route."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()


@router.get("/mappings", name="mappings", response_class=HTMLResponse)
async def mappings_page(
    request: Request, page: int = 1, per_page: int = 25, search: str | None = None
) -> HTMLResponse:
    """Render the mappings page.

    Args:
        request (Request): The HTTP request object.
        page (int): The page number to display.
        per_page (int): The number of items to display per page.
        search (str | None): The search query string.

    Returns:
        HTMLResponse: The rendered mappings page.
    """
    templates: Jinja2Templates = request.app.extra["templates"]
    return templates.TemplateResponse(
        "mappings.html.jinja", {"request": request, "search": search}
    )
