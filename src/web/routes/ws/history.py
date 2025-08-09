"""Websocket endpoint for live sync history timeline updates."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func

from src.config.database import db
from src.models.db.sync_history import SyncHistory, SyncOutcome

router = APIRouter()


@router.websocket("/{profile}")
async def history_ws(ws: WebSocket, profile: str) -> None:
    """Periodically push latest history page + stats to client.

    Args:
        ws (WebSocket): The WebSocket connection.
        profile (str): The profile name.
    """
    await ws.accept()
    last_ids: set[int] = set()

    try:
        while True:
            with db as ctx:
                q = (
                    ctx.session.query(SyncHistory)
                    .filter(SyncHistory.profile_name == profile)
                    .order_by(SyncHistory.timestamp.desc())
                )
                items = q.limit(100).all()

                stats_rows = (
                    ctx.session.query(SyncHistory.outcome, func.count(SyncHistory.id))
                    .filter(SyncHistory.profile_name == profile)
                    .group_by(SyncHistory.outcome)
                    .all()
                )

            stats = {o.value if hasattr(o, "value") else o: c for o, c in stats_rows}
            for o in SyncOutcome:
                stats.setdefault(o.value, 0)

            ids = {r.id for r in items}
            if ids != last_ids:
                last_ids = ids
                await ws.send_json(
                    {
                        "items": [r.model_dump(mode="json") for r in items],
                        "stats": stats,
                        "profile": profile,
                    }
                )
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass


__all__ = ["router"]
