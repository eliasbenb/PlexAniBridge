"""Sync history service with TTL caching."""

import logging
from typing import Any

import aiohttp
from async_lru import alru_cache
from pydantic import BaseModel
from sqlalchemy import func, select

from src.config.database import db
from src.models.db.sync_history import SyncHistory
from src.web.state import app_state

logger = logging.getLogger(__name__)


class HistoryItem(BaseModel):
    """Serializable history entry with optional AniList and Plex metadata."""

    id: int
    profile_name: str
    plex_guid: str | None = None
    plex_rating_key: str
    plex_child_rating_key: str | None = None
    plex_type: str
    anilist_id: int | None = None
    outcome: str
    before_state: dict | None = None
    after_state: dict | None = None
    error_message: str | None = None
    timestamp: str
    anilist: dict | None = None
    plex: dict | None = None


class HistoryPage(BaseModel):
    """Pagination wrapper for history items."""

    items: list[HistoryItem]
    total: int
    page: int
    per_page: int
    pages: int
    stats: dict[str, int]


class HistoryService:
    """Service to paginate and enrich sync history records."""

    def _get_bridge(self, profile: str):
        """Get the bridge client for a specific profile."""
        if not app_state.scheduler:
            raise ValueError("Scheduler not initialised")
        bridge = app_state.scheduler.bridge_clients.get(profile)
        if not bridge:
            raise ValueError(f"Unknown profile: {profile}")
        return bridge

    @alru_cache(maxsize=128, ttl=300)  # Cache for 5 minutes
    async def _fetch_anilist_batch(
        self, profile: str, ids_tuple: tuple[int, ...]
    ) -> dict[int, dict[str, Any]]:
        """Cached AniList batch fetch.

        Args:
            profile (str): Profile name to get the bridge client.
            ids_tuple (tuple[int, ...]): Tuple of AniList IDs to fetch (for hashing).

        Returns:
            Dictionary mapping AniList ID to serialized media data
        """
        bridge = self._get_bridge(profile)
        medias = await bridge.anilist_client.batch_get_anime(list(ids_tuple))

        result = {}
        for m in medias:
            m.media_list_entry = None
            result[m.id] = m.model_dump(mode="json")
        return result

    @alru_cache(maxsize=256, ttl=600)  # Cache for 10 minutes
    async def _fetch_plex_batch(
        self, profile: str, guids_tuple: tuple[str, ...]
    ) -> dict[str, dict[str, Any] | None]:
        """Cached Plex batch metadata fetch using comma-separated GUIDs.

        Args:
            profile (str): Profile name to get the bridge client.
            guids_tuple (tuple[str, ...]): Tuple of Plex GUIDs to fetch (for hashing).

        Returns:
            Dictionary mapping Plex GUID to serialized metadata or None if not found
        """
        if not guids_tuple:
            return {}

        bridge = self._get_bridge(profile)
        result: dict[str, dict[str, Any] | None] = {}

        guids_str = ",".join([guid.rsplit("/")[-1] for guid in guids_tuple if guid])

        # Use proper Plex API headers schema
        headers = {
            "Accept": "application/json",
            "X-Plex-Token": bridge.profile_config.plex_token,
        }

        try:
            # Plex public metadata API endpoint with comma-separated GUIDs
            url = f"https://metadata.provider.plex.tv/library/metadata/{guids_str}"

            async with (
                aiohttp.ClientSession(headers=headers) as session,
                session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response,
            ):
                # Handle token refresh on auth errors
                if response.status in (401, 403):
                    logger.warning(
                        f"Plex metadata API returned {response.status}, "
                        f"token may be expired for profile {profile}"
                    )
                    # Initialize all GUIDs as None on auth failure
                    for guid in guids_tuple:
                        result[guid] = None
                    return result

                if response.status != 200:
                    logger.warning(
                        f"Plex metadata API returned {response.status} for guids "
                        f"{guids_str}"
                    )
                    # Initialize all GUIDs as None on failure
                    for guid in guids_tuple:
                        result[guid] = None
                    return result

                data = await response.json()

                # Initialize all GUIDs as None first
                for guid in guids_tuple:
                    result[guid] = None

                # Extract metadata from Plex API response
                if "MediaContainer" in data and "Metadata" in data["MediaContainer"]:
                    metadata_items = data["MediaContainer"]["Metadata"]

                    for item in metadata_items:
                        if item["guid"] and item["guid"] in guids_tuple:
                            result[item["guid"]] = {
                                "guid": item["guid"],
                                "title": item.get("title", "Unknown Title"),
                                "type": item.get("type", "unknown"),
                                "art": item.get("art"),
                                "thumb": item.get("thumb"),
                            }

                return result

        except TimeoutError:
            logger.error(f"Timeout fetching Plex metadata for guids {guids_str}")
        except aiohttp.ClientError as e:
            logger.error(
                f"HTTP error fetching Plex metadata for guids {guids_str}: {e}"
            )
        except Exception as e:
            logger.error(f"Error fetching Plex metadata for guids {guids_str}: {e}")

        # Return None for all GUIDs on any error
        for guid in guids_tuple:
            result[guid] = None
        return result

    @alru_cache(maxsize=64, ttl=60)  # Cache stats for 1 minute
    async def _fetch_profile_stats(self, profile: str) -> dict[str, int]:
        """Cached profile statistics fetch.

        Args:
            profile: Profile name to get stats for

        Returns:
            Dictionary mapping outcome to count
        """
        with db as ctx:
            stats_rows = (
                ctx.session.query(SyncHistory.outcome, func.count(SyncHistory.id))
                .filter(SyncHistory.profile_name == profile)
                .group_by(SyncHistory.outcome)
                .all()
            )
            return {str(outcome): count for outcome, count in stats_rows}

    async def get_page(
        self,
        profile: str,
        page: int,
        per_page: int,
        outcome: str | None = None,
        include_anilist: bool = True,
        include_plex: bool = True,
    ) -> HistoryPage:
        """Return paginated history entries enriched as requested.

        Args:
            profile (str): The profile name to filter history entries.
            page (int): The page number to retrieve.
            per_page (int): The number of entries per page.
            outcome (str | None): Optional filter for the sync outcome.
            include_anilist (bool): Whether to include AniList metadata.
            include_plex (bool): Whether to include Plex metadata.

        Returns:
            HistoryPage: The paginated history entries.
        """
        page = max(1, page)
        per_page = max(1, min(per_page, 250))

        base_filters = [SyncHistory.profile_name == profile]
        if outcome:
            base_filters.append(SyncHistory.outcome == outcome)

        with db as ctx:
            # Get cached stats
            stats = await self._fetch_profile_stats(profile)

            count_stmt = (
                select(func.count()).select_from(SyncHistory).where(*base_filters)
            )
            total = ctx.session.execute(count_stmt).scalar_one()

            stmt = (
                select(SyncHistory)
                .where(*base_filters)
                .order_by(SyncHistory.timestamp.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
            rows = ctx.session.execute(stmt).scalars().all()

        # Fetch AniList data with caching
        anilist_map: dict[int, dict[str, Any]] = {}
        if include_anilist:
            ids = sorted({r.anilist_id for r in rows if r.anilist_id})
            if ids:
                anilist_map = await self._fetch_anilist_batch(profile, tuple(ids))

        # Fetch Plex data with batch caching
        plex_map: dict[str, dict[str, Any] | None] = {}
        if include_plex:
            guids = sorted({r.plex_guid for r in rows if r.plex_guid})

            if guids:
                plex_map = await self._fetch_plex_batch(profile, tuple(guids))

        dto_items: list[HistoryItem] = []
        for r in rows:
            dto_items.append(
                HistoryItem(
                    id=r.id,
                    profile_name=r.profile_name,
                    plex_guid=r.plex_guid,
                    plex_rating_key=r.plex_rating_key,
                    plex_child_rating_key=r.plex_child_rating_key,
                    plex_type=str(r.plex_type),
                    anilist_id=r.anilist_id,
                    outcome=str(r.outcome),
                    before_state=r.before_state,
                    after_state=r.after_state,
                    error_message=r.error_message,
                    timestamp=r.timestamp.isoformat(),
                    anilist=anilist_map.get(r.anilist_id) if r.anilist_id else None,
                    plex=plex_map.get(r.plex_guid) if r.plex_guid else None,
                )
            )

        return HistoryPage(
            items=dto_items,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page,
            stats=stats,
        )

    async def delete_item(self, profile: str, item_id: int) -> None:
        """Delete a single history item for a profile.

        Args:
            profile (str): The profile name.
            item_id (int): The ID of the history item to delete.
        """
        with db as ctx:
            row = (
                ctx.session.query(SyncHistory)
                .filter(SyncHistory.profile_name == profile, SyncHistory.id == item_id)
                .first()
            )
            if not row:
                raise ValueError("Not found")
            ctx.session.delete(row)
            ctx.session.commit()

        # Invalidate related caches after deletion
        await self.clear_profile_cache(profile)

    async def clear_profile_cache(self, profile: str) -> None:
        """Clear all cached data for a specific profile.

        Args:
            profile: Profile name to clear cache for
        """
        self._fetch_profile_stats.cache_clear()

    async def clear_all_caches(self) -> None:
        """Clear all caches."""
        self._fetch_anilist_batch.cache_clear()
        self._fetch_plex_batch.cache_clear()
        self._fetch_profile_stats.cache_clear()

    def get_cache_info(self) -> dict[str, Any]:
        """Get cache statistics for monitoring.

        Returns:
            Dictionary with cache hit/miss statistics
        """
        return {
            "anilist_cache": self._fetch_anilist_batch.cache_info(),
            "plex_cache": self._fetch_plex_batch.cache_info(),
            "stats_cache": self._fetch_profile_stats.cache_info(),
        }


history_service = HistoryService()
