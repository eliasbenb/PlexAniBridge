"""API endpoints for sync history timeline per profile."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import func

from src.config.database import db
from src.models.db.sync_history import SyncHistory, SyncOutcome

__all__ = ["router"]

router = APIRouter()


def _serialize(record: SyncHistory) -> dict[str, Any]:
    return {
        "id": record.id,
        "timestamp": record.timestamp.isoformat(),
        "plex_type": record.plex_type.value,
        "outcome": record.outcome.value,
        "anilist_id": record.anilist_id,
        "plex_rating_key": record.plex_rating_key,
        "plex_child_rating_key": record.plex_child_rating_key,
        "error_message": record.error_message,
        "before_state": record.before_state,
        "after_state": record.after_state,
        "plex_guid": record.plex_guid,
    }


@router.get("/{profile}")
async def history(profile: str, page: int = 1, per_page: int = 50) -> dict[str, Any]:
    """Return paginated sync history for a profile with aggregate stats.

    Args:
        profile (str): The profile name.
        page (int): The page number to retrieve.
        per_page (int): The number of items per page.

    Returns:
        dict[str, Any]: The paginated sync history for the profile.
    """
    if page < 1:
        raise HTTPException(400, "page must be >= 1")
    if per_page < 1 or per_page > 200:
        raise HTTPException(400, "per_page must be 1-200")
    with db as ctx:
        base_q = (
            ctx.session.query(SyncHistory)
            .filter(SyncHistory.profile_name == profile)
            .order_by(SyncHistory.timestamp.desc())
        )
        total = base_q.count()
        pages = (total + per_page - 1) // per_page if total else 1
        items = (
            base_q.offset((page - 1) * per_page).limit(per_page).all() if total else []
        )
        stats_rows = (
            ctx.session.query(SyncHistory.outcome, func.count(SyncHistory.id))
            .filter(SyncHistory.profile_name == profile)
            .group_by(SyncHistory.outcome)
            .all()
        )
    stats: dict[str, int] = {
        (o.value if isinstance(o, SyncOutcome) else o): c for o, c in stats_rows
    }
    for o in SyncOutcome:
        stats.setdefault(o.value, 0)
    return {
        "items": [_serialize(r) for r in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "stats": stats,
        "profile": profile,
    }


@router.get("/{profile}/latest")
async def latest_history(
    profile: str, since: str | None = None, limit: int = 100
) -> dict[str, Any]:
    """Return latest history items optionally since an ISO timestamp.

    Args:
        profile (str): The profile name.
        since (str | None): An optional ISO timestamp to filter results.
        limit (int): The maximum number of items to return.

    Returns:
        dict[str, Any]: The latest history items for the profile.
    """
    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(400, "Invalid 'since' timestamp") from None
    with db as ctx:
        q = (
            ctx.session.query(SyncHistory)
            .filter(SyncHistory.profile_name == profile)
            .order_by(SyncHistory.timestamp.desc())
        )
        if since_dt:
            q = q.filter(SyncHistory.timestamp > since_dt)
        items = q.limit(limit).all()
    return {"items": [_serialize(r) for r in items]}
