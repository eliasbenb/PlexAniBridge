"""Plex Webhook endpoint."""

from logging import DEBUG
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src import log
from src.config.settings import SyncMode
from src.models.schemas.plex import PlexWebhook, PlexWebhookEventType
from src.web.state import app_state

__all__ = ["router"]

router = APIRouter()


async def parse_webhook_request(request: Request) -> PlexWebhook:
    """Parse incoming webhook in either multipart or JSON format.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        PlexWebhook: The parsed webhook payload.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload_raw = form.get("payload")
        if not payload_raw:
            raise HTTPException(400, "Missing 'payload' form field")
        try:
            return PlexWebhook.model_validate_json(str(payload_raw))
        except Exception as e:
            raise HTTPException(400, f"Invalid payload JSON: {e}") from e
    # Fallback to JSON body
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON body: {e}") from e
    try:
        return PlexWebhook.model_validate(data)
    except Exception as e:
        raise HTTPException(400, f"Invalid payload structure: {e}") from e


@router.post("")
async def plex_webhook(
    request: Request,
    payload: PlexWebhook = Depends(parse_webhook_request),
) -> dict[str, Any]:
    """Receive Plex webhook and trigger a targeted sync.

    Args:
        request (Request): The incoming HTTP request.
        payload (PlexWebhook): The parsed webhook payload.

    Returns:
        A dictionary containing the result of the webhook processing.
    """
    if log.getEffectiveLevel() <= DEBUG:
        body = (
            (await request.body())
            .decode("utf-8", "replace")
            .translate({10: None, 13: None, 9: None, 32: None})  # Remove whitespace
            .strip()
        )
        log.debug(f"Received Plex webhook: {body}")

    scheduler = app_state.scheduler
    if not scheduler:
        raise HTTPException(503, "Scheduler not available")

    if not payload.account_id:
        raise HTTPException(400, "No account ID found in webhook payload")

    try:
        profile_name, profile_config = scheduler.get_profile_for_plex_account(
            payload.account_id
        )
    except KeyError as e:
        raise HTTPException(404, "Profile not found") from e

    if SyncMode.WEBHOOK not in profile_config.sync_modes:
        raise HTTPException(503, "Webhook sync mode is not enabled for this profile")

    profile_bridge = scheduler.bridge_clients.get(profile_name)
    if not profile_bridge:
        raise HTTPException(503, "Profile bridge not available")

    if payload.account_id is None:
        raise HTTPException(400, "No account ID found in webhook payload")
    if payload.account_id != profile_bridge.plex_client.user_account_id:
        raise HTTPException(403, "Account ID does not match profile")

    if payload.event not in (
        PlexWebhookEventType.MEDIA_ADDED,
        PlexWebhookEventType.RATE,
        PlexWebhookEventType.SCROBBLE,
    ):
        return {"ok": True, "processed_rating_key": None, "event": payload.event}

    if not payload.top_level_rating_key:
        raise HTTPException(400, "No rating key found in webhook payload")

    log.info(
        f"Webhook: Received Plex event {payload.event} with "
        f"rating_key={payload.top_level_rating_key} "
        f"targeting profile={profile_name or '*'}",
    )
    try:
        await scheduler.trigger_sync(
            profile_name=profile_name,
            poll=False,
            rating_keys=[payload.top_level_rating_key],
        )
    except KeyError:
        raise HTTPException(404, f"Profile '{profile_name}' not found") from None

    return {
        "ok": True,
        "processed_rating_key": payload.top_level_rating_key,
        "event": payload.event,
    }


@router.post("/{profile}")
async def _deprecated_plex_webhook_profile(
    request: Request,
    profile: str,
    payload: PlexWebhook = Depends(parse_webhook_request),
):
    """Deprecated webhook endpoint that took a profile name as a parameter."""
    return await plex_webhook(request, payload)
