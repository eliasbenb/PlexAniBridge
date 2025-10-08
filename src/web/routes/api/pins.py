"""API routes for managing AniList field pins."""

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from src.config.settings import SyncField
from src.web.services.pin_service import (
    PinEntry,
    PinFieldOption,
    UpdatePinPayload,
    get_pin_service,
)

router = APIRouter()


class PinListResponse(BaseModel):
    """Response model for listing pins."""

    pins: list[PinEntry]


class PinOptionsResponse(BaseModel):
    """Response model for available pin field options."""

    options: list[PinFieldOption]


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
async def list_pins(profile: str = Path(..., min_length=1)) -> PinListResponse:
    """List all pinned AniList entries for a profile.

    Args:
        profile (str): Profile name.

    Returns:
        PinListResponse: List of pinned entries.
    """
    service = get_pin_service()
    entries = service.list_pins(profile)
    return PinListResponse(pins=entries)


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
