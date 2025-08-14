"""API endpoints for sync history timeline per profile."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func

from src.config.database import db
from src.models.db.sync_history import SyncHistory, SyncOutcome

__all__ = ["router"]

router = APIRouter()


@router.get("/{profile}")
async def history(
    profile: str,
    page: int = 1,
    per_page: int = 50,
    outcome: str | None = Query(
        None,
        description=(
            "Optional outcome filter (synced, skipped, failed, not_found, deleted, "
            "pending)"
        ),
    ),
) -> dict[str, Any]:
    """Return paginated sync history for a profile with aggregate stats.

    Args:
        profile (str): The profile name.
        page (int): The page number to retrieve.
        per_page (int): The number of items per page.
        outcome (str | None): Optional SyncOutcome value to filter results server side.

    Returns:
        dict[str, Any]: The (optionally filtered) paginated sync history for the
            profile.
    """
    if page < 1:
        raise HTTPException(400, "page must be >= 1")
    if per_page < 1 or per_page > 200:
        raise HTTPException(400, "per_page must be 1-200")
    outcome_enum: SyncOutcome | None = None
    if outcome is not None:
        try:
            outcome_enum = SyncOutcome(outcome)
        except ValueError as e:
            raise HTTPException(400, f"invalid outcome '{outcome}'") from e
    with db as ctx:
        base_q = (
            ctx.session.query(SyncHistory)
            .filter(SyncHistory.profile_name == profile)
            .order_by(SyncHistory.timestamp.desc())
        )
        if outcome_enum is not None:
            base_q = base_q.filter(SyncHistory.outcome == outcome_enum)
        total = base_q.count()
        pages = (total + per_page - 1) // per_page if total else 1
        items = (
            base_q.offset((page - 1) * per_page).limit(per_page).all() if total else []
        )
        # Stats are always computed across the entire profile (unfiltered) so UI can
        # display global counts even when a server-side filter is active.
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
        "items": [r.model_dump(mode="json") for r in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "stats": stats,
        "profile": profile,
        "outcome_filter": outcome_enum.value if outcome_enum else None,
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
    return {"items": [r.model_dump(mode="json") for r in items]}
