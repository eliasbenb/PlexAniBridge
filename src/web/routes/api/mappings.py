"""API endpoints for mappings - list from AniMap DB, edit via custom overrides."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, column, exists, func, or_, select

from src.config.database import db
from src.models.db.animap import AniMap
from src.models.schemas.anilist import MediaWithoutList as AniListMetadata
from src.web.services.mappings_store import get_mappings_store
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
    custom: bool = False
    anilist: AniListMetadata | None = None


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
    page: int = 1,
    per_page: int = 25,
    search: str | None = None,
    custom_only: bool = False,
    with_anilist: bool = False,
) -> ListMappingsResponse:
    """List mappings from AniMap database with optional search and pagination.

    Edits are stored separately as overrides and merged into the result.
    """
    where_clauses = []
    if search:
        s = search.strip()
        num = None
        try:
            num = int(s) if s.isdigit() else None
        except ValueError:
            num = None

        or_parts = []
        if num is not None:
            or_parts.extend(
                [
                    # Direct ID matches
                    *(
                        getattr(AniMap, k) == num
                        for k in ["tmdb_movie_id", "tmdb_show_id", "mal_id"]
                    ),
                    # JSONB containment
                    *(
                        exists(
                            select(1)
                            .select_from(func.json_each(getattr(AniMap, k)))
                            .where(column("value") == num)
                        )
                        for k in ["tmdb_movie_id", "tmdb_show_id", "mal_id"]
                    ),
                ]
            )
        if s.lower().startswith("tt"):
            or_parts.append(
                exists(
                    select(1)
                    .select_from(func.json_each(AniMap.imdb_id))
                    .where(column("value") == s)
                )
            )
        if or_parts:
            where_clauses.append(or_(*or_parts))

    store = get_mappings_store()
    custom_ids: set[int] | None = None
    if custom_only:
        # Preload custom override IDs for filtering query.
        custom_ids = set(store.keys())
        if not custom_ids:
            return ListMappingsResponse(
                items=[],
                total=0,
                page=page,
                per_page=per_page,
                pages=0,
                with_anilist=with_anilist,
            )
        where_clauses.append(AniMap.anilist_id.in_(custom_ids))

    with db() as ctx:
        base_query = select(AniMap)
        count_query = select(func.count()).select_from(AniMap)
        if where_clauses:
            wc = and_(*where_clauses)
            base_query = base_query.where(wc)
            count_query = count_query.where(wc)

        total = ctx.session.execute(count_query).scalar_one()
        base_query = (
            base_query.order_by(AniMap.anilist_id)
            .offset(max(0, (page - 1) * per_page))
            .limit(per_page)
        )
        rows = ctx.session.execute(base_query).scalars().all()

    scheduler = get_app_state().scheduler

    items = list(rows)

    enriched_map: dict[int, AniListMetadata] = {}
    if with_anilist and scheduler and scheduler.bridge_clients:
        first_bridge = next(iter(scheduler.bridge_clients.values()))
        try:
            medias = await first_bridge.anilist_client.batch_get_anime(
                [it.anilist_id for it in items if it.anilist_id]
            )
            for m in medias:
                d = m.model_dump(mode="json")
                d.pop("media_list_entry", None)
                enriched_map[m.id] = AniListMetadata(**d)
        except Exception:
            pass

    store_overrides = get_mappings_store()
    overrides: dict[int, dict[str, Any]] = {}

    for override_id in list(store_overrides.keys()):
        ov = store_overrides.get(override_id)
        if ov:
            overrides[override_id] = ov

    result_items: list[MappingItemModel] = []
    for it in items:
        ov = overrides.get(it.anilist_id) or {}
        result_items.append(
            MappingItemModel(
                anilist_id=it.anilist_id,
                anidb_id=ov.get("anidb_id", it.anidb_id),
                imdb_id=ov.get("imdb_id", it.imdb_id),
                mal_id=ov.get("mal_id", it.mal_id),
                tmdb_movie_id=ov.get("tmdb_movie_id", it.tmdb_movie_id),
                tmdb_show_id=ov.get("tmdb_show_id", it.tmdb_show_id),
                tvdb_id=ov.get("tvdb_id", it.tvdb_id),
                tvdb_mappings=ov.get("tvdb_mappings", it.tvdb_mappings),
                custom=bool(ov),
                anilist=enriched_map.get(it.anilist_id),
            )
        )
    return ListMappingsResponse(
        items=result_items,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
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
    store = get_mappings_store()
    scheduler = get_app_state().scheduler
    res = store.upsert(mapping)
    if not scheduler:
        raise HTTPException(503, "Scheduler not available")
    await scheduler.shared_animap_client._sync_db()

    res_obj = MappingItemModel(**res)
    return res_obj


@router.put("/{mapping_id}", response_model=MappingItemModel)
async def update_mapping(mapping_id: int, mapping: dict[str, Any]) -> MappingItemModel:
    """Update an existing custom mapping.

    Args:
        mapping_id (int): The ID of the mapping to update.
        mapping (dict[str, Any]): The updated mapping data.

    Returns:
        dict[str, Any]: The updated mapping.
    """
    store = get_mappings_store()
    scheduler = get_app_state().scheduler
    mapping["anilist_id"] = mapping_id
    res = store.upsert(mapping)
    if not scheduler:
        raise HTTPException(503, "Scheduler not available")
    await scheduler.shared_animap_client._sync_db()
    return MappingItemModel(**res)


@router.get("/{mapping_id}", response_model=MappingItemModel)
async def get_mapping(mapping_id: int) -> MappingItemModel:
    """Retrieve a single custom mapping by ID.

    Args:
        mapping_id (int): The ID of the mapping to retrieve.

    Returns:
        dict[str, Any]: The mapping data.
    """
    store = get_mappings_store()
    m = store.get(mapping_id)
    if not m:
        raise HTTPException(404, "Not found")
    return MappingItemModel(**m)


@router.delete("/{mapping_id}", response_model=DeleteMappingResponse)
async def delete_mapping(mapping_id: int) -> DeleteMappingResponse:
    """Delete a custom mapping.

    Args:
        mapping_id (int): The ID of the mapping to delete.

    Returns:
        dict[str, Any]: A confirmation message.
    """
    store = get_mappings_store()
    scheduler = get_app_state().scheduler
    if not store.delete(mapping_id):
        raise HTTPException(404, "Not found")
    if not scheduler:
        raise HTTPException(503, "Scheduler not available")
    await scheduler.shared_animap_client._sync_db()
    return DeleteMappingResponse(ok=True)
