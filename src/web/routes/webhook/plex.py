"""Plex Webhook endpoint."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src import log
from src.config.settings import SyncMode
from src.web.state import app_state

__all__ = ["router"]

router = APIRouter()


class PlexWebhookPayload(BaseModel):
    event: str | None = None
    Metadata: dict[str, Any] | None = None

    def rating_key(self) -> str | None:
        """Extract the top level rating key.

        Returns:
            str | None: The extracted rating key or None if not found.
        """
        if not self.Metadata:
            return None
        for k in ("grandparentRatingKey", "parentRatingKey", "ratingKey"):
            v = self.Metadata.get(k)
            if v is not None:
                return str(v)
        return None


async def parse_webhook_request(request: Request) -> PlexWebhookPayload:
    """Parse incoming webhook in either multipart or JSON format.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        PlexWebhookPayload: The parsed webhook payload.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload_raw = form.get("payload")
        if not payload_raw:
            raise HTTPException(400, "Missing 'payload' form field")
        try:
            return PlexWebhookPayload.model_validate_json(str(payload_raw))
        except Exception as e:
            raise HTTPException(400, f"Invalid payload JSON: {e}") from e
    # Fallback to JSON body
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON body: {e}") from e
    try:
        return PlexWebhookPayload.model_validate(data)
    except Exception as e:
        raise HTTPException(400, f"Invalid payload structure: {e}") from e


@router.post("/{profile}")
async def plex_webhook(
    profile: str,
    payload: PlexWebhookPayload = Depends(parse_webhook_request),  # noqa: B008
) -> dict[str, Any]:
    """Receive Plex webhook and trigger a targeted sync.

    Args:
        profile (str): The profile name to target for the sync.
        payload (PlexWebhookPayload): The parsed webhook payload.

    Returns:
        A dictionary containing the result of the webhook processing.
    """
    scheduler = app_state.scheduler
    if not scheduler:
        raise HTTPException(503, "Scheduler not available")

    profile_config = scheduler.global_config.get_profile(profile)

    if SyncMode.WEBHOOK not in profile_config.sync_modes:
        raise HTTPException(503, "Webhook sync mode is not enabled for this profile")

    if payload.event not in ("library.new", "media.rate", "media.scrobble"):
        return {"ok": True, "processed_rating_key": None, "event": payload.event}

    rating_key = payload.rating_key()
    if not rating_key:
        raise HTTPException(400, "No rating key found in webhook payload")

    log.info(
        f"Webhook: Received Plex event {payload.event} with rating_key={rating_key} "
        f"targeting profile={profile or '*'}",
    )
    try:
        await scheduler.trigger_sync(
            profile_name=profile, poll=False, rating_keys=[rating_key]
        )
    except KeyError:
        raise HTTPException(404, f"Profile '{profile}' not found") from None

    return {"ok": True, "processed_rating_key": rating_key, "event": payload.event}
