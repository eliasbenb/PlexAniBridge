"""API routes for application metrics."""

from datetime import datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from src.config.database import db
from src.models.db.sync_history import SyncHistory, SyncOutcome

router = APIRouter()


class MetricPoint(BaseModel):
    """Metric data point."""

    timestamp: datetime
    value: int


class MetricsResponse(BaseModel):
    """Metrics response model."""

    total_syncs: int
    sync_activity: list[MetricPoint]
    outcome_distribution: dict[str, int]


@router.get("/", response_model=MetricsResponse)
async def get_metrics() -> MetricsResponse:
    """Get application metrics."""
    with db as ctx:
        # Get all sync history
        query = select(SyncHistory)
        all_results = ctx.session.execute(query).scalars().all()

        total_syncs = len(all_results)

        # Get outcome distribution
        outcome_distribution = {}
        for outcome in SyncOutcome:
            count = len([r for r in all_results if r.outcome == outcome])
            if count > 0:  # Only include outcomes that have occurred
                outcome_distribution[outcome.value] = count

        # Get sync activity for the last 7 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        sync_activity = []
        for i in range(7):
            day_start = start_date + timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            day_syncs = len(
                [r for r in all_results if day_start <= r.timestamp < day_end]
            )

            sync_activity.append(MetricPoint(timestamp=day_start, value=day_syncs))

        return MetricsResponse(
            total_syncs=total_syncs,
            sync_activity=sync_activity,
            outcome_distribution=outcome_distribution,
        )


# Updated template response for HTMX requests
@router.get("/template")
async def get_metrics_template():
    """Get metrics as HTML template for HTMX updates."""
    metrics = await get_metrics()

    # This would be called from HTMX, so we need to render the template
    # For now, return the data structure that the template expects
    return {
        "total_syncs": metrics.total_syncs,
        "sync_activity": [
            {"timestamp": p.timestamp, "value": p.value} for p in metrics.sync_activity
        ],
        "outcome_distribution": metrics.outcome_distribution,
    }
