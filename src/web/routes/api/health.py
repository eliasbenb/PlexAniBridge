"""Health check API routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.config.settings import PlexAnibridgeConfig
from src.core.sched import SchedulerClient
from src.web.dependencies import get_config, get_scheduler

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    version: str
    scheduler_running: bool
    profiles_count: int


@router.get("/", response_model=HealthResponse)
async def health_check(
    config: PlexAnibridgeConfig = Depends(get_config),
    scheduler: SchedulerClient = Depends(get_scheduler),
) -> HealthResponse:
    """Health check endpoint."""
    from src import __version__

    return HealthResponse(
        status="healthy",
        version=__version__,
        scheduler_running=scheduler._running,
        profiles_count=len(config.profiles),
    )
