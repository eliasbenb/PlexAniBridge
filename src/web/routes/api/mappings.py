"""API endpoints for mappings - list from AniMap DB, edit via custom overrides."""

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, column, exists, func, or_, select

from src.config.database import db
from src.models.db.animap import AniMap
from src.web.services.mappings_store import get_mappings_store
from src.web.state import app_state

__all__ = ["router"]

router = APIRouter()


@router.get("")
async def list_mappings(
    page: int = 1, per_page: int = 25, search: str | None = None
) -> dict[str, Any]:
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
                    AniMap.anilist_id == num,
                    AniMap.anidb_id == num,
                    AniMap.tvdb_id == num,
                    exists(
                        select(1)
                        .select_from(func.json_each(AniMap.tmdb_movie_id))
                        .where(column("value") == num)
                    ),
                    exists(
                        select(1)
                        .select_from(func.json_each(AniMap.tmdb_show_id))
                        .where(column("value") == num)
                    ),
                    exists(
                        select(1)
                        .select_from(func.json_each(AniMap.mal_id))
                        .where(column("value") == num)
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

    with db as ctx:
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

    def row_to_dict(a: AniMap) -> dict[str, Any]:
        return {
            "anilist_id": a.anilist_id,
            "anidb_id": a.anidb_id,
            "imdb_id": a.imdb_id,
            "mal_id": a.mal_id,
            "tmdb_movie_id": a.tmdb_movie_id,
            "tmdb_show_id": a.tmdb_show_id,
            "tvdb_id": a.tvdb_id,
            "tvdb_mappings": a.tvdb_mappings,
        }

    items = [row_to_dict(r) for r in rows]

    # Merge overrides from store
    store = get_mappings_store()
    for i, item in enumerate(items):
        ov = store.get(item["anilist_id"])
        if ov:
            merged = {**item, **{k: v for k, v in ov.items() if k != "anilist_id"}}
            merged["custom"] = True
            items[i] = merged
        else:
            item["custom"] = False

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.post("")
async def create_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Create a new custom mapping.

    Args:
        mapping (dict[str, Any]): The mapping data to create.

    Returns:
        dict[str, Any]: The created mapping.
    """
    store = get_mappings_store()
    return store.upsert(mapping)


@router.put("/{mapping_id}")
async def update_mapping(mapping_id: int, mapping: dict[str, Any]) -> dict[str, Any]:
    """Update an existing custom mapping.

    Args:
        mapping_id (int): The ID of the mapping to update.
        mapping (dict[str, Any]): The updated mapping data.

    Returns:
        dict[str, Any]: The updated mapping.
    """
    store = get_mappings_store()
    mapping["anilist_id"] = mapping_id
    return store.upsert(mapping)


@router.get("/{mapping_id}")
async def get_mapping(mapping_id: int) -> dict[str, Any]:
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
    return m


@router.delete("/{mapping_id}")
async def delete_mapping(mapping_id: int) -> dict[str, Any]:
    """Delete a custom mapping.

    Args:
        mapping_id (int): The ID of the mapping to delete.

    Returns:
        dict[str, Any]: A confirmation message.
    """
    store = get_mappings_store()
    if not store.delete(mapping_id):
        raise HTTPException(404, "Not found")
    if not app_state.scheduler:
        raise HTTPException(503, "Scheduler not available")
    await app_state.scheduler.shared_animap_client._sync_db()
    return {"ok": True}
