"""Core Module Initialization."""

from src.core.anilist import AniListClient
from src.core.animap import AniMapClient
from src.core.plex import PlexClient

from src.core.bridge import BridgeClient  # isort:skip
from src.core.sched import SchedulerClient

__all__ = [
    "AniListClient",
    "AniMapClient",
    "PlexClient",
    "BridgeClient",
    "SchedulerClient",
]
