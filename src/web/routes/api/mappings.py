"""API endpoints for mappings."""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select

from src.config.database import db
from src.exceptions import MappingIdMismatchError, MappingNotFoundError
from src.models.db.animap import AniMap
from src.models.db.provenance import AniMapProvenance
from src.models.schemas.anilist import MediaWithoutList as AniListMetadata
from src.utils.sql import json_array_contains, json_dict_has_key, json_dict_has_value
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


router = APIRouter()


@router.get("", response_model=ListMappingsResponse)
async def list_mappings(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=250),
    search: str | None = None,
    custom_only: bool = False,
    with_anilist: bool = False,
) -> ListMappingsResponse:
    """List mappings from AniMap database with optional search and pagination.

    Edits are stored separately as overrides and merged into the result.

    Args:
        page (int): Page number (1-based).
        per_page (int): Number of items per page (max 250).
        search (str | None): Optional search term to filter mappings.
        custom_only (bool): If true, only include mappings that have been customized
            (i.e. last provenance source is not the current upstream URL).
        with_anilist (bool): If true, include AniList metadata in the response.

    Returns:
        ListMappingsResponse: The paginated list of mappings.
    """
    search_filters: list[Any] = []
    if search:
        search_num: int | None = None
        try:
            search_num = int(search)
        except ValueError:
            search_num = None

        per_col = []
        if search_num is not None:
            per_col.append(AniMap.anilist_id == search_num)
            per_col.append(AniMap.anidb_id == search_num)
            per_col.append(AniMap.tvdb_id == search_num)
            per_col.append(json_array_contains(AniMap.mal_id, [search_num]))
            per_col.append(json_array_contains(AniMap.tmdb_movie_id, [search_num]))
            per_col.append(json_array_contains(AniMap.tmdb_show_id, [search_num]))

        per_col.append(json_array_contains(AniMap.imdb_id, [search]))
        per_col.append(json_dict_has_key(AniMap.tvdb_mappings, search))
        per_col.append(json_dict_has_value(AniMap.tvdb_mappings, search))
        search_filters.append(or_(*per_col))

    with db() as ctx:
        stmt = select(AniMap)

        sub = (
            select(
                AniMapProvenance.anilist_id,
                func.max(AniMapProvenance.n).label("maxn"),
            )
            .group_by(AniMapProvenance.anilist_id)
            .subquery()
        )
        stmt = (
            stmt.outerjoin(sub, sub.c.anilist_id == AniMap.anilist_id)
            .outerjoin(
                AniMapProvenance,
                and_(
                    AniMapProvenance.anilist_id == sub.c.anilist_id,
                    AniMapProvenance.n == sub.c.maxn,
                ),
            )
            .add_columns(AniMapProvenance.source)
        )

        # Apply filters
        where_clauses: list[Any] = []
        if search_filters:
            where_clauses.extend(search_filters)

        # Filter for custom_only: last source != current upstream URL
        scheduler = get_app_state().scheduler
        upstream_url = scheduler.global_config.mappings_url if scheduler else None
        if custom_only:
            if upstream_url:
                where_clauses.append(
                    and_(
                        AniMapProvenance.source.is_not(None),
                        AniMapProvenance.source != upstream_url,
                    )
                )
            else:
                # No upstream configured: treat any non-null source as custom
                where_clauses.append(AniMapProvenance.source.is_not(None))

        if where_clauses:
            stmt = stmt.where(and_(*where_clauses))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = ctx.session.execute(count_stmt).scalar_one()

        # Pagination
        stmt = (
            stmt.order_by(AniMap.anilist_id.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        rows = ctx.session.execute(stmt).all()

        items: list[MappingItemModel] = []
        anilist_ids: list[int] = []

        for row in rows:
            animap: AniMap = row[0]
            anilist_ids.append(animap.anilist_id)

        # Fetch all provenance sources for the page items
        sources_by_id: dict[int, list[str]] = {aid: [] for aid in anilist_ids}
        if anilist_ids:
            prov_rows = ctx.session.execute(
                select(
                    AniMapProvenance.anilist_id,
                    AniMapProvenance.n,
                    AniMapProvenance.source,
                )
                .where(AniMapProvenance.anilist_id.in_(anilist_ids))
                .order_by(
                    AniMapProvenance.anilist_id.asc(),
                    AniMapProvenance.n.asc(),
                )
            ).all()
            for aid, _n, src in prov_rows:
                sources_by_id.setdefault(aid, []).append(src)

        # Build items with sources and custom flag from last source
        for row in rows:
            animap: AniMap = row[0]
            srcs = sources_by_id.get(animap.anilist_id, [])
            last_src = srcs[-1] if srcs else None
            is_custom = bool(
                last_src is not None and (not upstream_url or last_src != upstream_url)
            )
            items.append(
                MappingItemModel(
                    anilist_id=animap.anilist_id,
                    anidb_id=animap.anidb_id,
                    imdb_id=animap.imdb_id,
                    mal_id=animap.mal_id,
                    tmdb_movie_id=animap.tmdb_movie_id,
                    tmdb_show_id=animap.tmdb_show_id,
                    tvdb_id=animap.tvdb_id,
                    tvdb_mappings=animap.tvdb_mappings,
                    custom=is_custom,
                    sources=srcs,
                )
            )

    if with_anilist and items:
        scheduler = get_app_state().scheduler
        if scheduler and scheduler.bridge_clients:
            # Use the first available profile's AniList client
            bridge = next(iter(scheduler.bridge_clients.values()))
            medias = await bridge.anilist_client.batch_get_anime(anilist_ids)
            by_id = {m.id: m for m in medias}

            for it in items:
                m = by_id.get(it.anilist_id)
                if m:
                    it.anilist = AniListMetadata(
                        **{
                            k: getattr(m, k)
                            for k in AniListMetadata.model_fields
                            if hasattr(m, k)
                        }
                    )

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
    """
    svc = get_mappings_service()
    svc.delete_mapping(mapping_id)
    return DeleteMappingResponse(ok=True)
