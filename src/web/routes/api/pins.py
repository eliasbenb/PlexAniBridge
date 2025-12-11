"""API routes for managing field pins across list providers."""

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from aiohttp import ClientError
from fastapi.exceptions import HTTPException
from fastapi.param_functions import Path, Query
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from src.config.settings import SyncField
from src.models.schemas.provider import ProviderMediaMetadata
from src.web.services.pin_service import (
    PinEntry,
    PinFieldOption,
    UpdatePinPayload,
    get_pin_service,
)
from src.web.state import get_app_state

if TYPE_CHECKING:
    from anibridge.list import ListEntry, ListProvider

    from src.core.bridge import BridgeClient

router = APIRouter()


class PinListResponse(BaseModel):
    """Response model for listing pins."""

    pins: list[PinEntry]


class PinOptionsResponse(BaseModel):
    """Response model for available pin field options."""

    options: list[PinFieldOption]


class PinSearchItem(BaseModel):
    """Search result item combining provider metadata with existing pin state."""

    media: ProviderMediaMetadata
    pin: PinEntry | None = None


class PinSearchResponse(BaseModel):
    """Response model for provider search results within the pin manager."""

    results: list[PinSearchItem]


class UpdatePinRequest(BaseModel):
    """Request body for updating pin fields."""

    fields: list[SyncField | str] = Field(default_factory=list)

    def to_payload(self) -> UpdatePinPayload:
        """Convert request into payload for the service layer."""
        payload = UpdatePinPayload(fields=[])
        normalized: list[str] = []
        for field in self.fields:
            value = field.value if isinstance(field, SyncField) else str(field)
            normalized.append(value)
        payload.fields = normalized
        return payload


class OkResponse(BaseModel):
    """Response model for successful operations."""

    ok: bool = True


def _get_bridge(profile: str) -> BridgeClient:
    state = get_app_state()
    scheduler = state.scheduler
    if not scheduler:
        raise HTTPException(503, detail="Scheduler not available")
    bridge = scheduler.bridge_clients.get(profile)
    if not bridge:
        raise HTTPException(status_code=404, detail="Unknown profile")
    return bridge


def _list_identifiers(entries: Iterable[PinEntry]) -> list[tuple[str, str]]:
    identifiers: list[tuple[str, str]] = []
    for entry in entries:
        if entry.list_media_key:
            identifiers.append((entry.list_namespace, entry.list_media_key))
    return identifiers


async def _fetch_list_metadata(
    profile: str,
    identifiers: Sequence[tuple[str, str]],
) -> dict[tuple[str, str], ProviderMediaMetadata]:
    if not identifiers:
        return {}

    bridge = _get_bridge(profile)
    provider: ListProvider = bridge.list_provider
    namespace = provider.NAMESPACE
    scoped = [(ns, key) for ns, key in identifiers if ns == namespace and key]
    if not scoped:
        return {}

    keys = [key for _, key in scoped]
    try:
        entries = await provider.get_entries_batch(keys)
    except ClientError as exc:
        raise HTTPException(502, detail="Failed to fetch provider metadata") from exc
    except Exception as exc:
        raise HTTPException(500, detail="Failed to fetch provider metadata") from exc

    metadata: dict[tuple[str, str], ProviderMediaMetadata] = {}
    for (_namespace, _key), entry in zip(scoped, entries, strict=False):
        if entry is None:
            continue
        media = entry.media()
        metadata[(namespace, media.key)] = ProviderMediaMetadata(
            namespace=namespace,
            key=media.key,
            title=media.title,
            poster_url=media.poster_image,
        )
    return metadata


def _search_result_metadata(namespace: str, entry: ListEntry) -> ProviderMediaMetadata:
    media = entry.media()
    title = media.title or entry.title or None
    return ProviderMediaMetadata(
        namespace=namespace,
        key=media.key,
        title=title,
        poster_url=media.poster_image,
    )


@router.get("/fields", response_model=PinOptionsResponse)
def get_pin_fields() -> PinOptionsResponse:
    """Return selectable pin field metadata."""
    service = get_pin_service()
    return PinOptionsResponse(options=service.list_options())


@router.get("/{profile}", response_model=PinListResponse)
async def list_pins(
    profile: str = Path(..., min_length=1),
    with_media: bool = Query(False, description="Include provider metadata for pins."),
) -> PinListResponse:
    """List all pinned list entries for a profile.

    Args:
        profile (str): Profile name.
        with_media (bool): Include media metadata for each pin when true.

    Returns:
        PinListResponse: List of pinned entries.
    """
    service = get_pin_service()
    entries = service.list_pins(profile)
    if not with_media or not entries:
        return PinListResponse(pins=entries)

    metadata = await _fetch_list_metadata(profile, _list_identifiers(entries))
    enriched = [
        entry.model_copy(
            update={"media": metadata.get((entry.list_namespace, entry.list_media_key))}
        )
        for entry in entries
    ]
    return PinListResponse(pins=enriched)


@router.get("/{profile}/search", response_model=PinSearchResponse)
async def search_pins(
    profile: str = Path(..., min_length=1),
    q: str | None = Query(None, min_length=1),
    limit: int = Query(10, ge=1, le=50),
) -> PinSearchResponse:
    """Search list entries to manage pins against.

    Args:
        profile (str): Profile name to scope existing pins.
        q (str | None): Text query to search AniList titles.
        limit (int): Maximum number of search results to return.

    Returns:
        PinSearchResponse: Matched AniList titles with pin status.
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Provide a search query")

    bridge = _get_bridge(profile)
    provider: ListProvider = bridge.list_provider

    service = get_pin_service()
    existing = {
        (entry.list_namespace, entry.list_media_key): entry
        for entry in service.list_pins(profile)
    }

    try:
        results = await provider.search(query)
    except ClientError as exc:
        raise HTTPException(502, detail="Failed to query list provider") from exc
    except Exception as exc:
        raise HTTPException(500, detail="Failed to query list provider") from exc

    items: list[PinSearchItem] = []
    seen: set[tuple[str, str]] = set()
    for entry in results:
        identifier = (provider.NAMESPACE, entry.media().key)
        if identifier in seen:
            continue
        seen.add(identifier)
        metadata = _search_result_metadata(provider.NAMESPACE, entry)
        pin = existing.get(identifier)
        if pin is not None:
            pin = pin.model_copy(update={"media": metadata})
        items.append(PinSearchItem(media=metadata, pin=pin))
        if len(items) >= limit:
            break

    return PinSearchResponse(results=items)


@router.get("/{profile}/{namespace}/{media_key}", response_model=PinEntry)
async def get_pin(
    profile: str = Path(..., min_length=1),
    namespace: str = Path(..., min_length=1),
    media_key: str = Path(..., min_length=1),
    with_media: bool = Query(False),
) -> PinEntry:
    """Retrieve pin configuration for a specific list entry.

    Args:
        profile (str): Profile name.
        namespace (str): List namespace.
        media_key (str): Media key.
        with_media (bool): Include media metadata for the pin when true.

    Returns:
        PinEntry: Pin configuration.
    """
    service = get_pin_service()
    entry = service.get_pin(profile, namespace, media_key)
    if not entry:
        raise HTTPException(status_code=404, detail="Pin not found")

    if not with_media:
        return entry

    metadata = await _fetch_list_metadata(profile, [(namespace, media_key)])
    return entry.model_copy(update={"media": metadata.get((namespace, media_key))})


@router.put("/{profile}/{namespace}/{media_key}", response_model=PinEntry)
async def upsert_pin(
    request: UpdatePinRequest,
    profile: str = Path(..., min_length=1),
    namespace: str = Path(..., min_length=1),
    media_key: str = Path(..., min_length=1),
    with_media: bool = Query(False),
) -> PinEntry:
    """Create or update pin fields for a media item."""
    payload = request.to_payload()
    try:
        entry = get_pin_service().upsert_pin(
            profile, namespace, media_key, payload.normalized()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not with_media:
        return entry

    metadata = await _fetch_list_metadata(profile, [(namespace, media_key)])
    return entry.model_copy(update={"media": metadata.get((namespace, media_key))})


@router.delete("/{profile}/{namespace}/{media_key}", response_model=OkResponse)
def delete_pin(
    profile: str = Path(..., min_length=1),
    namespace: str = Path(..., min_length=1),
    media_key: str = Path(..., min_length=1),
) -> OkResponse:
    """Delete pin configuration for an list entry.

    Args:
        profile (str): Profile name.
        namespace (str): List namespace.
        media_key (str): Media key.

    Returns:
        OkResponse: Confirmation of successful deletion.
    """
    get_pin_service().delete_pin(profile, namespace, media_key)
    return OkResponse()
