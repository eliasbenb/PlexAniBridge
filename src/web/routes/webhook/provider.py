"""Provider Webhook endpoint."""

from fastapi.routing import APIRouter
from starlette.requests import Request

from src import log
from src.exceptions import SchedulerNotInitializedError
from src.web.state import get_app_state

__all__ = ["router"]

router = APIRouter()


@router.post("/{provider_namespace}")
async def provider_webhook(
    provider_namespace: str,
    request: Request,
) -> None:
    """Receive Provider webhook and trigger a targeted sync.

    Args:
        provider_namespace (str): The provider namespace from the URL path.
        request (Request): The incoming HTTP request.
    """
    log.info(f"Webhoo: Received webhook for provider '{provider_namespace}'")
    scheduler = get_app_state().scheduler
    if not scheduler:
        log.warning("Webhook: Scheduler not available")
        raise SchedulerNotInitializedError("Scheduler not available")

    candidates = scheduler.get_profiles_for_library_provider(provider_namespace)
    for profile_name in candidates:
        try:
            is_valid, library_keys = await scheduler.bridge_clients[
                profile_name
            ].parse_webhook(request)
            if not is_valid:
                continue

            log.info(
                f"Webhook: Triggering sync for profile '{profile_name}' "
                f"and library keys: {library_keys}"
            )
            await scheduler.trigger_sync(
                profile_name=profile_name,
                poll=False,
                library_keys=library_keys,
            )
        except KeyError:
            log.error(f"Webhook: No bridge client found for profile '{profile_name}'")
            continue
