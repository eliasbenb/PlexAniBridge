"""Plex Webhook endpoint."""

from typing import Any

from fastapi.param_functions import Depends
from fastapi.routing import APIRouter
from starlette.requests import Request

from src import log
from src.config.settings import SyncMode
from src.exceptions import (
    InvalidWebhookPayloadError,
    ProfileNotFoundError,
    SchedulerNotInitializedError,
    WebhookModeDisabledError,
)
from src.models.schemas.plex import PlexWebhook, PlexWebhookEventType
from src.web.state import get_app_state

__all__ = ["router"]

router = APIRouter()


async def parse_webhook_request(request: Request) -> PlexWebhook:
    """Parse incoming webhook in either multipart or JSON format.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        PlexWebhook: The parsed webhook payload.

    Raises:
        InvalidWebhookPayloadError: If the request body or payload is invalid.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload_raw = form.get("payload")
        if not payload_raw:
            raise InvalidWebhookPayloadError("Missing 'payload' form field")
        try:
            return PlexWebhook.model_validate_json(str(payload_raw))
        except Exception as e:
            raise InvalidWebhookPayloadError(f"Invalid payload JSON: {e}") from e
    # Fallback to JSON body
    try:
        data = await request.json()
    except Exception as e:
        raise InvalidWebhookPayloadError(f"Invalid JSON body: {e}") from e
    try:
        return PlexWebhook.model_validate(data)
    except Exception as e:
        raise InvalidWebhookPayloadError(f"Invalid payload structure: {e}") from e


@router.post("")
async def plex_webhook(
    payload: PlexWebhook = Depends(parse_webhook_request),
) -> dict[str, Any]:
    """Receive Plex webhook and trigger a targeted sync.

    Args:
        payload (PlexWebhook): The parsed webhook payload.

    Returns:
        A dictionary containing the result of the webhook processing.

    Raises:
        SchedulerNotInitializedError: If the scheduler is not running.
        InvalidWebhookPayloadError: If the payload is invalid.
        ProfileNotFoundError: If no profiles match the account id.
        WebhookModeDisabledError: If webhook sync mode is disabled for the profile.
    """
    scheduler = get_app_state().scheduler
    if not scheduler:
        log.warning("Webhook: Scheduler not available")
        raise SchedulerNotInitializedError("Scheduler not available")

    if not payload.account_id:
        log.debug("Webhook: No account ID found in payload")
        raise InvalidWebhookPayloadError("No account ID found in webhook payload")

    if not payload.top_level_rating_key:
        log.debug("Webhook: No rating key found in payload")
        raise InvalidWebhookPayloadError("No rating key found in webhook payload")

    if payload.event not in (
        PlexWebhookEventType.MEDIA_ADDED,
        PlexWebhookEventType.RATE,
        PlexWebhookEventType.SCROBBLE,
    ):
        log.debug(f"Webhook: Ignoring unsupported event type '{payload.event}'")
        return {"ok": True, "processed_rating_key": None, "event": payload.event}

    try:
        profiles = [
            p
            for p in scheduler.get_profiles_for_plex_account(payload.account_id)
            if SyncMode.WEBHOOK in p[1].sync_modes
        ]
    except KeyError as e:
        log.debug(f"Webhook: No profiles found for account ID '{payload.account_id}'")
        raise ProfileNotFoundError("Profile not found") from e

    if not profiles:
        log.debug("Webhook: No profiles found for account ID '{payload.account_id}'")
        raise WebhookModeDisabledError(
            "Webhook sync mode is not enabled for this profile"
        )

    log.info(
        f"Webhook: Received Plex event {payload.event} with "
        f"rating_key={payload.top_level_rating_key} "
        f"target_profiles={', '.join(p[0] for p in profiles)}"
    )

    success = False
    for profile_name, _ in profiles:
        try:
            await scheduler.trigger_sync(
                profile_name=profile_name,
                poll=False,
                rating_keys=[payload.top_level_rating_key],
            )
            success = True
        except KeyError:
            log.error(f"Webhook: No bridge client found for profile '{profile_name}'")
            continue

    return {
        "ok": success,
        "processed_rating_key": payload.top_level_rating_key,
        "event": payload.event,
    }
