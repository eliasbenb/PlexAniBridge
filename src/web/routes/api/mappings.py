"""API endpoints for mappings."""

import asyncio
from enum import Enum
from typing import Any

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.param_functions import Query
from fastapi.routing import APIRouter
from pydantic import BaseModel, model_validator

from src.exceptions import MappingIdMismatchError
from src.models.schemas.anilist import MediaWithoutList
from src.web.services.mapping_overrides_service import (
    get_mapping_overrides_service,
)
from src.web.services.mappings_query_spec import (
    QueryFieldOperator,
    QueryFieldSpec,
    QueryFieldType,
    get_query_field_specs,
)
from src.web.services.mappings_service import get_mappings_service

__all__ = ["router"]


class MappingItemModel(BaseModel):
    """Flattened mapping item with optional AniList metadata."""

    anilist_id: int
    anidb_id: int | None = None
    imdb_id: list[str] | None = None
    mal_id: list[int] | None = None
    tmdb_movie_id: list[int] | None = None
    tmdb_show_id: int | None = None
    tvdb_id: int | None = None
    tmdb_mappings: dict[str, str] | None = None
    tvdb_mappings: dict[str, str] | None = None
    anilist: MediaWithoutList | None = None
    custom: bool = False
    sources: list[str] = []


class ListMappingsResponse(BaseModel):
    items: list[MappingItemModel]
    total: int
    page: int
    per_page: int
    pages: int
    with_anilist: bool = False


class DeleteMappingResponse(BaseModel):
    ok: bool


class MappingOverrideMode(str, Enum):
    """Supported modes for mapping override fields."""

    OMIT = "omit"
    NULL = "null"
    VALUE = "value"


class MappingOverrideFieldInput(BaseModel):
    """Input model for a single mapping override field."""

    mode: MappingOverrideMode = MappingOverrideMode.VALUE
    value: Any | None = None


class MappingOverridePayload(BaseModel):
    """Payload for creating or updating a mapping override."""

    anilist_id: int
    fields: dict[str, MappingOverrideFieldInput] | None = None
    raw: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _ensure_payload(self) -> "MappingOverridePayload":
        """Ensure at least one of fields or raw is provided."""
        if self.fields is None and self.raw is None:
            raise ValueError("Either 'fields' or 'raw' must be provided")
        return self


class MappingDetailModel(MappingItemModel):
    """Mapping model including override data."""

    override: dict[str, Any] | None = None


class OverrideDeleteKind(str, Enum):
    """Supported deletion behaviours for mapping overrides."""

    CUSTOM = "custom"
    FULL = "full"


def _prepare_override_kwargs(
    payload: MappingOverridePayload,
) -> dict[str, Any]:
    """Prepare keyword arguments for mapping override service methods."""
    fields_data: dict[str, Any] | None = None
    if payload.fields:
        fields_data = {key: field.model_dump() for key, field in payload.fields.items()}
    return {
        "anilist_id": payload.anilist_id,
        "fields": fields_data,
        "raw": payload.raw,
    }


class FieldCapability(BaseModel):
    """Describes supported operators and value type for a query field."""

    key: str
    aliases: list[str] = []
    type: QueryFieldType
    operators: list[QueryFieldOperator]
    values: list[str] | None = None  # for enums like has:*
    desc: str | None = None


class QueryCapabilitiesResponse(BaseModel):
    fields: list[FieldCapability]


router = APIRouter()


@router.get("/query-capabilities", response_model=QueryCapabilitiesResponse)
async def get_query_capabilities() -> QueryCapabilitiesResponse:
    """Return supported operators for each queryable field.

    This allows the frontend to tailor suggestions based on backend capabilities.
    """
    specs: tuple[QueryFieldSpec, ...] = get_query_field_specs()
    fields = [
        FieldCapability(
            key=spec.key,
            aliases=list(spec.aliases),
            type=spec.type,
            operators=list(spec.operators),
            values=list(spec.values) if spec.values else None,
            desc=spec.desc,
        )
        for spec in specs
    ]

    return QueryCapabilitiesResponse(fields=fields)


@router.get("", response_model=ListMappingsResponse)
async def list_mappings(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=250),
    q: str | None = None,
    custom_only: bool = False,
    with_anilist: bool = False,
) -> ListMappingsResponse:
    """List mappings from AniMap database with optional search and pagination.

    Args:
        request (Request): Active request context for cancellation handling.
        page (int): 1-based page number.
        per_page (int): Number of items per page.
        q (str | None): Booru-like query string.
        custom_only (bool): Include only custom mappings.
        with_anilist (bool): Include AniList metadata.

    Returns:
        ListMappingsResponse: The paginated list of mappings.
    """
    svc = get_mappings_service()

    async def cancel_check() -> bool:
        return await request.is_disconnected()

    try:
        raw_items, total = await svc.list_mappings(
            page=page,
            per_page=per_page,
            q=q,
            custom_only=custom_only,
            with_anilist=with_anilist,
            cancel_check=cancel_check,
        )
    except asyncio.CancelledError as exc:
        raise HTTPException(status_code=499, detail="Client Closed Request") from exc

    items = [MappingItemModel(**it) for it in raw_items]
    pages = (total + per_page - 1) // per_page if per_page else 1
    return ListMappingsResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        with_anilist=with_anilist,
    )


@router.post("", response_model=MappingDetailModel)
async def create_mapping(mapping: MappingOverridePayload) -> MappingDetailModel:
    """Create a new custom mapping.

    Args:
        mapping (MappingOverridePayload): The mapping data to create.

    Returns:
        MappingDetailModel: The created mapping detail including overrides.

    Raises:
        MissingAnilistIdError: If anilist_id is not provided.
        UnsupportedMappingFileExtensionError: If the custom file extension is
            unsupported.
    """
    svc = get_mapping_overrides_service()
    payload = _prepare_override_kwargs(mapping)
    data = await svc.save_override(**payload)
    return MappingDetailModel(**data)


@router.put("/{mapping_id}", response_model=MappingDetailModel)
async def update_mapping(
    mapping_id: int, mapping: MappingOverridePayload
) -> MappingDetailModel:
    """Update an existing custom mapping.

    Args:
        mapping_id (int): The ID of the mapping to update.
        mapping (MappingOverridePayload): The updated mapping data.

    Returns:
        MappingDetailModel: The updated mapping detail.

    Raises:
        MappingIdMismatchError: If anilist_id in the body does not match the URL.
        UnsupportedMappingFileExtensionError: If the custom file extension is
            unsupported.
    """
    if mapping.anilist_id != mapping_id:
        raise MappingIdMismatchError(
            "anilist_id in body must match the mapping_id path parameter"
        )

    svc = get_mapping_overrides_service()
    data = await svc.save_override(**_prepare_override_kwargs(mapping))
    return MappingDetailModel(**data)


@router.get("/{mapping_id}", response_model=MappingDetailModel)
async def get_mapping(mapping_id: int) -> MappingDetailModel:
    """Retrieve a single mapping by ID.

    Args:
        mapping_id (int): The ID of the mapping to retrieve.

    Returns:
        MappingDetailModel: The mapping data with override details.

    Raises:
        MappingNotFoundError: If the mapping does not exist.
    """
    svc = get_mapping_overrides_service()
    data = await svc.get_mapping_detail(mapping_id)
    return MappingDetailModel(**data)


@router.delete("/{mapping_id}", response_model=DeleteMappingResponse)
async def delete_mapping(
    mapping_id: int,
    kind: OverrideDeleteKind = OverrideDeleteKind.CUSTOM,
) -> DeleteMappingResponse:
    """Delete a mapping.

    Args:
        mapping_id (int): The ID of the mapping to delete.
        kind (OverrideDeleteKind): Deletion strategy to apply.

    Returns:
        DeleteMappingResponse: A confirmation message.

    Raises:
        UnsupportedMappingFileExtensionError: If the custom file extension is
            unsupported.
    """
    svc = get_mapping_overrides_service()
    await svc.delete_override(mapping_id, mode=kind.value)
    return DeleteMappingResponse(ok=True)
