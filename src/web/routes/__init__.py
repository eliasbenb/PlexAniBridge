"""Web server routes for PlexAniBridge."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from src.web.routes.api import router as api_router
from src.web.routes.dashboard import router as dashboard_router
from src.web.routes.logs import router as logs_router
from src.web.routes.profiles import router as profiles_router
from src.web.routes.ws import router as ws_router

router = APIRouter()


# Redirect root to dashboard
@router.get("/")
async def root():
    """Redirect root to dashboard."""
    return RedirectResponse(url="/dashboard/", status_code=302)


router.include_router(api_router, prefix="/api")
router.include_router(dashboard_router, prefix="/dashboard")
router.include_router(logs_router, prefix="/logs")
router.include_router(profiles_router, prefix="/profiles")
router.include_router(ws_router, prefix="/ws")
