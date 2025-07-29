"""Profiles API routes."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select

from src.config.database import db
from src.config.settings import PlexAnibridgeConfig
from src.models.db.sync_history import MediaType, SyncHistory, SyncOutcome
from src.web.dependencies import get_config

router = APIRouter()


class SyncHistoryItem(BaseModel):
    """Sync history item model."""

    id: int
    plex_guid: str | None
    plex_rating_key: str
    plex_child_rating_key: str | None
    plex_type: MediaType
    anilist_id: int | None
    outcome: SyncOutcome
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    error_message: str | None
    timestamp: datetime


class ProfileHistoryResponse(BaseModel):
    """Profile history response model."""

    profile_name: str
    total_items: int
    items: list[SyncHistoryItem]


@router.get("/{profile_name}/history", response_model=ProfileHistoryResponse)
async def get_profile_history(
    profile_name: str,
    config: PlexAnibridgeConfig = Depends(get_config),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ProfileHistoryResponse:
    """Get sync history for a profile."""
    if profile_name not in config.profiles:
        raise HTTPException(status_code=404, detail="Profile not found")

    with db as ctx:
        # Get total count
        total_query = select(SyncHistory).where(
            SyncHistory.profile_name == profile_name
        )
        total_count = len(ctx.session.execute(total_query).scalars().all())

        # Get paginated results
        query = (
            select(SyncHistory)
            .where(SyncHistory.profile_name == profile_name)
            .order_by(desc(SyncHistory.timestamp))
            .limit(limit)
            .offset(offset)
        )

        results = ctx.session.execute(query).scalars().all()

        items = []
        for result in results:
            item = SyncHistoryItem(
                id=result.id,
                plex_guid=result.plex_guid,
                plex_rating_key=result.plex_rating_key,
                plex_child_rating_key=result.plex_child_rating_key,
                plex_type=result.plex_type,
                anilist_id=result.anilist_id,
                outcome=result.outcome,
                before_state=result.before_state,
                after_state=result.after_state,
                error_message=result.error_message,
                timestamp=result.timestamp,
            )
            items.append(item)

        return ProfileHistoryResponse(
            profile_name=profile_name,
            total_items=total_count,
            items=items,
        )


@router.get("/{profile_name}/stats")
async def get_profile_stats(
    profile_name: str,
    config: PlexAnibridgeConfig = Depends(get_config),
) -> dict[str, Any]:
    """Get sync statistics for a profile."""
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

        return stats
