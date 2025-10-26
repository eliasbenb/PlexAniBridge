"""API endpoints for mappings."""

import asyncio
from typing import Any

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.param_functions import Query
from fastapi.routing import APIRouter
from pydantic import BaseModel

from src.models.schemas.anilist import MediaWithoutList
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


@router.post("", response_model=MappingItemModel)
async def create_mapping(mapping: dict[str, Any]) -> MappingItemModel:
    """Create a new custom mapping.

    Args:
        mapping (dict[str, Any]): The mapping data to create.

    Returns:
        dict[str, Any]: The created mapping.

    Raises:
        MissingAnilistIdError: If anilist_id is not provided.
        UnsupportedMappingFileExtensionError: If the custom file extension is
            unsupported.
    """
    pass


@router.put("/{mapping_id}", response_model=MappingItemModel)
async def update_mapping(mapping_id: int, mapping: dict[str, Any]) -> MappingItemModel:
    """Update an existing custom mapping.

    Args:
        mapping_id (int): The ID of the mapping to update.
        mapping (dict[str, Any]): The updated mapping data.

    Returns:
        dict[str, Any]: The updated mapping.

    Raises:
        MappingIdMismatchError: If anilist_id in the body does not match the URL.
        UnsupportedMappingFileExtensionError: If the custom file extension is
            unsupported.
    """
    pass


@router.get("/{mapping_id}", response_model=MappingItemModel)
async def get_mapping(mapping_id: int) -> MappingItemModel:
    """Retrieve a single mapping by ID.

    Args:
        mapping_id (int): The ID of the mapping to retrieve.

    Returns:
        dict[str, Any]: The mapping data.

    Raises:
        MappingNotFoundError: If the mapping does not exist.
    """
    pass


@router.delete("/{mapping_id}", response_model=DeleteMappingResponse)
async def delete_mapping(mapping_id: int) -> DeleteMappingResponse:
    """Delete a mapping.

    Args:
        mapping_id (int): The ID of the mapping to delete.

    Returns:
        dict[str, Any]: A confirmation message.

    Raises:
        UnsupportedMappingFileExtensionError: If the custom file extension is
            unsupported.
    """
    pass
