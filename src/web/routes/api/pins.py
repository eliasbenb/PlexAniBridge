"""API routes for managing AniList field pins."""

from aiohttp import ClientError
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from src.config.settings import SyncField
from src.models.schemas.anilist import MediaWithoutList as AniListMetadata
from src.web.services.pin_service import (
    PinEntry,
    PinFieldOption,
    UpdatePinPayload,
    get_pin_service,
)
from src.web.state import get_app_state

router = APIRouter()


class PinListResponse(BaseModel):
    """Response model for listing pins."""

    pins: list[PinEntry]


class PinOptionsResponse(BaseModel):
    """Response model for available pin field options."""

    options: list[PinFieldOption]


class PinSearchItem(BaseModel):
    """Search result item combining AniList metadata with existing pin state."""

    anilist: AniListMetadata
    pin: PinEntry | None = None


class PinSearchResponse(BaseModel):
    """Response model for AniList search results within the pin manager."""

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


@router.get("/fields", response_model=PinOptionsResponse)
async def get_pin_fields() -> PinOptionsResponse:
    """Return selectable pin field metadata.

    Returns:
        PinOptionsResponse: Available pin field options.
    """
    service = get_pin_service()
    return PinOptionsResponse(options=service.list_options())


@router.get("/{profile}", response_model=PinListResponse)
async def list_pins(
    profile: str = Path(..., min_length=1),
    with_anilist: bool = Query(False),
) -> PinListResponse:
    """List all pinned AniList entries for a profile.

    Args:
        profile (str): Profile name.
        with_anilist (bool): Include AniList metadata for each pin when true.

    Returns:
        PinListResponse: List of pinned entries.
    """
    service = get_pin_service()
    entries = service.list_pins(profile)
    if with_anilist and entries:
        try:
            client = await get_app_state().ensure_public_anilist()
            media_list = await client.batch_get_anime(
                [entry.anilist_id for entry in entries]
            )
        except ClientError as exc:
            raise HTTPException(502, detail="Failed to fetch AniList metadata") from exc
        media_by_id = {
            int(media.id): AniListMetadata.model_validate(
                media.model_dump(exclude_none=True)
            )
            for media in media_list
            if getattr(media, "id", None) is not None
        }
        entries = [
            entry.model_copy(update={"anilist": media_by_id.get(entry.anilist_id)})
            if media_by_id.get(entry.anilist_id)
            else entry
            for entry in entries
        ]
    return PinListResponse(pins=entries)


@router.get("/{profile}/search", response_model=PinSearchResponse)
async def search_pins(
    profile: str = Path(..., min_length=1),
    q: str | None = Query(None, min_length=1),
    limit: int = Query(10, ge=1, le=50),
) -> PinSearchResponse:
    """Search AniList for entries to manage pins against.

    Args:
        profile (str): Profile name to scope existing pins.
        q (str | None): Text query to search AniList titles.
        limit: Maximum number of search results to return.

    Returns:
        PinSearchResponse: Matched AniList titles with pin status.
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Provide a search query")

    service = get_pin_service()
    existing = {entry.anilist_id: entry for entry in service.list_pins(profile)}

    try:
        client = await get_app_state().ensure_public_anilist()
    except Exception as exc:
        raise HTTPException(503, detail="AniList client unavailable") from exc

    results: list[PinSearchItem] = []
    seen: set[int] = set()

    async def add_media(media) -> None:
        if media is None or getattr(media, "id", None) is None:
            return
        aid = int(media.id)
        if aid in seen:
            return
        seen.add(aid)
        metadata = AniListMetadata.model_validate(media.model_dump(exclude_none=True))
        pin = existing.get(aid)
        if pin is not None:
            pin = pin.model_copy(update={"anilist": metadata})
        results.append(PinSearchItem(anilist=metadata, pin=pin))

    try:
        if query:
            try:
                count = 0
                async for media in client.search_anime(
                    query,
                    is_movie=None,
                    episodes=None,
                    limit=limit,
                ):
                    await add_media(media)
                    count += 1
                    if count >= limit:
                        break
            except ClientError as exc:
                raise HTTPException(502, detail="Failed to query AniList") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            500, detail="Unexpected error during AniList search"
        ) from exc

    return PinSearchResponse(results=results)


@router.get("/{profile}/{anilist_id}", response_model=PinEntry)
async def get_pin(
    profile: str = Path(..., min_length=1),
    anilist_id: int = Path(..., ge=1),
) -> PinEntry:
    """Retrieve pin configuration for a specific AniList entry.

    Args:
        profile (str): Profile name.
        anilist_id (int): AniList ID.

    Returns:
        PinEntry: Pin configuration.
    """
    service = get_pin_service()
    entry = service.get_pin(profile, anilist_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Pin not found")
    return entry


@router.put("/{profile}/{anilist_id}", response_model=PinEntry)
async def upsert_pin(
    request: UpdatePinRequest,
    profile: str = Path(..., min_length=1),
    anilist_id: int = Path(..., ge=1),
) -> PinEntry:
    """Create or update pin fields for an AniList entry.

    Args:
        request (UpdatePinRequest): Request body with fields to pin.
        profile (str): Profile name.
        anilist_id (int): AniList ID.

    Returns:
        PinEntry: Updated pin configuration.
    """
    payload = request.to_payload()
    try:
        entry = get_pin_service().upsert_pin(profile, anilist_id, payload.normalized())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return entry


@router.delete("/{profile}/{anilist_id}", response_model=OkResponse)
async def delete_pin(
    profile: str = Path(..., min_length=1),
    anilist_id: int = Path(..., ge=1),
) -> OkResponse:
    """Delete pin configuration for an AniList entry.

    Args:
        profile (str): Profile name.
        anilist_id (int): AniList ID.

    Returns:
        OkResponse: Confirmation of successful deletion.
    """
    get_pin_service().delete_pin(profile, anilist_id)
    return OkResponse()
