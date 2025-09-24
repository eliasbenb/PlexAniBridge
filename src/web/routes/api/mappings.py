"""API endpoints for mappings."""

from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from src.config.database import db
from src.exceptions import MappingIdMismatchError, MappingNotFoundError
from src.models.db.animap import AniMap
from src.models.db.provenance import AniMapProvenance
from src.models.schemas.anilist import MediaWithoutList as AniListMetadata
from src.web.services.mappings_service import get_mappings_service
from src.web.state import get_app_state

__all__ = ["router"]


class MappingItemModel(BaseModel):
    """Flattened mapping item with optional AniList metadata."""

    anilist_id: int
    anidb_id: int | None = None
    imdb_id: list[str] | None = None
    mal_id: list[int] | None = None
    tmdb_movie_id: list[int] | None = None
    tmdb_show_id: list[int] | None = None
    tvdb_id: int | None = None
    tvdb_mappings: dict[str, str] | None = None
    anilist: AniListMetadata | None = None
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


class FieldType(StrEnum):
    INT = "int"
    STRING = "string"
    ENUM = "enum"


class FieldOperator(StrEnum):
    EQ = "="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    RANGE = "range"


class FieldCapability(BaseModel):
    """Describes supported operators and value type for a query field."""

    key: str
    aliases: list[str] = []
    type: FieldType
    operators: list[FieldOperator]
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
    has_values = [
        "anilist",
        "id",
        "anidb",
        "imdb",
        "mal",
        "tmdb_movie",
        "tmdb_show",
        "tvdb",
        "tvdb_mappings",
    ]

    fields = [
        FieldCapability(
            key="anilist",
            aliases=["id"],
            type=FieldType.INT,
            operators=[
                FieldOperator.EQ,
                FieldOperator.GT,
                FieldOperator.GTE,
                FieldOperator.LT,
                FieldOperator.LTE,
                FieldOperator.RANGE,
            ],
            desc="AniList ID",
        ),
        FieldCapability(
            key="anidb",
            type=FieldType.INT,
            operators=[
                FieldOperator.EQ,
                FieldOperator.GT,
                FieldOperator.GTE,
                FieldOperator.LT,
                FieldOperator.LTE,
                FieldOperator.RANGE,
            ],
            desc="AniDB ID",
        ),
        FieldCapability(
            key="imdb",
            type=FieldType.STRING,
            operators=[FieldOperator.EQ],
            desc="IMDb ID",
        ),
        FieldCapability(
            key="mal",
            type=FieldType.INT,
            operators=[
                FieldOperator.EQ,
                FieldOperator.GT,
                FieldOperator.GTE,
                FieldOperator.LT,
                FieldOperator.LTE,
                FieldOperator.RANGE,
            ],
            desc="MyAnimeList ID",
        ),
        FieldCapability(
            key="tmdb_movie",
            type=FieldType.INT,
            operators=[
                FieldOperator.EQ,
                FieldOperator.GT,
                FieldOperator.GTE,
                FieldOperator.LT,
                FieldOperator.LTE,
                FieldOperator.RANGE,
            ],
            desc="TMDb Movie ID",
        ),
        FieldCapability(
            key="tmdb_show",
            type=FieldType.INT,
            operators=[
                FieldOperator.EQ,
                FieldOperator.GT,
                FieldOperator.GTE,
                FieldOperator.LT,
                FieldOperator.LTE,
                FieldOperator.RANGE,
            ],
            desc="TMDb TV Show ID",
        ),
        FieldCapability(
            key="tvdb",
            type=FieldType.INT,
            operators=[
                FieldOperator.EQ,
                FieldOperator.GT,
                FieldOperator.GTE,
                FieldOperator.LT,
                FieldOperator.LTE,
                FieldOperator.RANGE,
            ],
            desc="TVDB ID",
        ),
        FieldCapability(
            key="tvdb_mappings",
            type=FieldType.STRING,
            operators=[FieldOperator.EQ],
            desc="Season/episode mappings",
        ),
        FieldCapability(
            key="has",
            type=FieldType.ENUM,
            operators=[FieldOperator.EQ],
            values=has_values,
            desc="Presence filter",
        ),
    ]

    return QueryCapabilitiesResponse(fields=fields)


@router.get("", response_model=ListMappingsResponse)
async def list_mappings(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=250),
    q: str | None = None,
    custom_only: bool = False,
    with_anilist: bool = False,
) -> ListMappingsResponse:
    """List mappings from AniMap database with optional search and pagination.

    Args:
        page (int): 1-based page number.
        per_page (int): Number of items per page.
        q (str | None): Booru-like query string.
        custom_only (bool): Include only custom mappings.
        with_anilist (bool): Include AniList metadata.

    Returns:
        ListMappingsResponse: The paginated list of mappings.
    """
    svc = get_mappings_service()
    raw_items, total = await svc.list_mappings(
        page=page,
        per_page=per_page,
        q=q,
        custom_only=custom_only,
        with_anilist=with_anilist,
    )

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
    svc = get_mappings_service()
    obj = svc.replace_mapping(mapping)

    # Compute provenance to set flags
    scheduler = get_app_state().scheduler
    upstream_url = scheduler.global_config.mappings_url if scheduler else None
    # Get last source via provenance
    with db() as ctx:
        sub = (
            select(
                AniMapProvenance.anilist_id,
                func.max(AniMapProvenance.n).label("maxn"),
            )
            .where(AniMapProvenance.anilist_id == obj.anilist_id)
            .group_by(AniMapProvenance.anilist_id)
            .subquery()
        )

        src = ctx.session.execute(
            select(AniMapProvenance.source).join(
                sub,
                and_(
                    AniMapProvenance.anilist_id == sub.c.anilist_id,
                    AniMapProvenance.n == sub.c.maxn,
                ),
            )
        ).scalar_one_or_none()

        # Fetch full ordered sources for this mapping
        prov_list = (
            ctx.session.execute(
                select(AniMapProvenance.source)
                .where(AniMapProvenance.anilist_id == obj.anilist_id)
                .order_by(AniMapProvenance.n.asc())
            )
            .scalars()
            .all()
        )

    return MappingItemModel(
        anilist_id=obj.anilist_id,
        anidb_id=obj.anidb_id,
        imdb_id=obj.imdb_id,
        mal_id=obj.mal_id,
        tmdb_movie_id=obj.tmdb_movie_id,
        tmdb_show_id=obj.tmdb_show_id,
        tvdb_id=obj.tvdb_id,
        tvdb_mappings=obj.tvdb_mappings,
        custom=(src is not None and (not upstream_url or src != upstream_url)),
        sources=list(prov_list),
    )


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
    if mapping.get("anilist_id") and int(mapping["anilist_id"]) != mapping_id:
        raise MappingIdMismatchError("anilist_id in body does not match URL")

    svc = get_mappings_service()
    obj = svc.upsert_mapping(mapping_id, mapping)

    scheduler = get_app_state().scheduler
    upstream_url = scheduler.global_config.mappings_url if scheduler else None
    with db() as ctx:
        sub = (
            select(
                AniMapProvenance.anilist_id,
                func.max(AniMapProvenance.n).label("maxn"),
            )
            .where(AniMapProvenance.anilist_id == obj.anilist_id)
            .group_by(AniMapProvenance.anilist_id)
            .subquery()
        )

        src = ctx.session.execute(
            select(AniMapProvenance.source).join(
                sub,
                and_(
                    AniMapProvenance.anilist_id == sub.c.anilist_id,
                    AniMapProvenance.n == sub.c.maxn,
                ),
            )
        ).scalar_one_or_none()

        prov_list = (
            ctx.session.execute(
                select(AniMapProvenance.source)
                .where(AniMapProvenance.anilist_id == obj.anilist_id)
                .order_by(AniMapProvenance.n.asc())
            )
            .scalars()
            .all()
        )

    return MappingItemModel(
        anilist_id=obj.anilist_id,
        anidb_id=obj.anidb_id,
        imdb_id=obj.imdb_id,
        mal_id=obj.mal_id,
        tmdb_movie_id=obj.tmdb_movie_id,
        tmdb_show_id=obj.tmdb_show_id,
        tvdb_id=obj.tvdb_id,
        tvdb_mappings=obj.tvdb_mappings,
        custom=(src is not None and (not upstream_url or src != upstream_url)),
        sources=list(prov_list),
    )


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
    with db() as ctx:
        obj = ctx.session.get(AniMap, mapping_id)
        if not obj:
            raise MappingNotFoundError("Mapping not found")

        sub = (
            select(
                AniMapProvenance.anilist_id,
                func.max(AniMapProvenance.n).label("maxn"),
            )
            .where(AniMapProvenance.anilist_id == obj.anilist_id)
            .group_by(AniMapProvenance.anilist_id)
            .subquery()
        )

        src = ctx.session.execute(
            select(AniMapProvenance.source).join(
                sub,
                and_(
                    AniMapProvenance.anilist_id == sub.c.anilist_id,
                    AniMapProvenance.n == sub.c.maxn,
                ),
            )
        ).scalar_one_or_none()

    # Gather full provenance list for this mapping
    scheduler = get_app_state().scheduler
    upstream_url = scheduler.global_config.mappings_url if scheduler else None
    with db() as ctx2:
        prov_list = (
            ctx2.session.execute(
                select(AniMapProvenance.source)
                .where(AniMapProvenance.anilist_id == obj.anilist_id)
                .order_by(AniMapProvenance.n.asc())
            )
            .scalars()
            .all()
        )
    return MappingItemModel(
        anilist_id=obj.anilist_id,
        anidb_id=obj.anidb_id,
        imdb_id=obj.imdb_id,
        mal_id=obj.mal_id,
        tmdb_movie_id=obj.tmdb_movie_id,
        tmdb_show_id=obj.tmdb_show_id,
        tvdb_id=obj.tvdb_id,
        tvdb_mappings=obj.tvdb_mappings,
        custom=(src is not None and (not upstream_url or src != upstream_url)),
        sources=list(prov_list),
    )


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
    svc = get_mappings_service()
    svc.delete_mapping(mapping_id)
    return DeleteMappingResponse(ok=True)
