"""Sync history service with TTL caching."""

import logging
from collections import defaultdict
from collections.abc import Sequence
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from async_lru import alru_cache
from fastapi.param_functions import Query
from pydantic import BaseModel
from sqlalchemy import func, select

from src import log
from src.config.database import db
from src.exceptions import (
    HistoryItemNotFoundError,
    ProfileNotFoundError,
    SchedulerNotInitializedError,
)
from src.models.db.pin import Pin
from src.models.db.sync_history import SyncHistory
from src.models.schemas.provider import ProviderMediaMetadata
from src.web.state import get_app_state

if TYPE_CHECKING:
    from anibridge.library import LibraryProvider, LibrarySection
    from anibridge.list import ListProvider

    from src.core.bridge import BridgeClient

__all__ = ["HistoryService", "get_history_service"]

logger = logging.getLogger(__name__)


class HistoryItem(BaseModel):
    """Serializable history entry with optional provider metadata."""

    id: int
    profile_name: str
    library_namespace: str | None = None
    library_section_key: str | None = None
    library_media_key: str | None = None
    list_namespace: str | None = None
    list_media_key: str | None = None
    media_kind: str | None = None
    outcome: str
    before_state: dict | None = None
    after_state: dict | None = None
    error_message: str | None = None
    timestamp: str
    library_media: ProviderMediaMetadata | None = None
    list_media: ProviderMediaMetadata | None = None
    pinned_fields: list[str] | None = None


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

    def _get_bridge(self, profile: str) -> BridgeClient:
        """Return the bridge client for a specific profile."""
        scheduler = get_app_state().scheduler
        if not scheduler:
            raise SchedulerNotInitializedError("Scheduler not available")
        bridge = scheduler.bridge_clients.get(profile)
        if not bridge:
            raise ProfileNotFoundError(f"Unknown profile: {profile}")
        return bridge

    @alru_cache(ttl=300)
    async def _fetch_list_metadata_batch(
        self, profile: str, namespace: str, keys_tuple: tuple[str, ...]
    ) -> dict[str, ProviderMediaMetadata]:
        """Fetch list provider metadata for a batch of media keys."""
        if not keys_tuple:
            return {}
        bridge = self._get_bridge(profile)
        provider: ListProvider = bridge.list_provider
        if namespace != provider.NAMESPACE:
            return {}

        entries = await provider.get_entries_batch(list(keys_tuple))
        metadata: dict[str, ProviderMediaMetadata] = {}
        for entry in entries:
            if entry is None:
                continue
            media = entry.media()
            metadata[media.key] = ProviderMediaMetadata(
                namespace=namespace,
                key=media.key,
                title=media.title,
                poster_url=media.poster_image,
            )
        return metadata

    @alru_cache(ttl=300)
    async def _fetch_library_metadata_batch(
        self,
        profile: str,
        namespace: str,
        section_key: str | None,
        media_keys: tuple[str, ...],
    ) -> dict[str, ProviderMediaMetadata]:
        if not media_keys:
            return {}

        bridge = self._get_bridge(profile)
        provider: LibraryProvider = bridge.library_provider
        if namespace != provider.NAMESPACE:
            return {}

        sections: Sequence[LibrarySection] = await provider.get_sections()
        target_sections: list[LibrarySection]
        if section_key is None:
            target_sections = list(sections)
        else:
            target_sections = [
                section for section in sections if section.key == section_key
            ]
            if not target_sections:
                return {}

        remaining = set(media_keys)
        metadata: dict[str, ProviderMediaMetadata] = {}
        for section in target_sections:
            if not remaining:
                break
            items = await provider.list_items(section, keys=list(remaining))
            for item in items:
                key = str(item.key)
                if key not in remaining:
                    continue
                remaining.discard(key)
                metadata[key] = ProviderMediaMetadata(
                    namespace=namespace,
                    key=key,
                    title=item.title,
                    poster_url=item.poster_image,
                )
        return metadata

    @alru_cache(ttl=60)
    async def _fetch_profile_stats(self, profile: str) -> dict[str, int]:
        """Cached profile statistics fetch."""
        with db() as ctx:
            stats_rows = (
                ctx.session.query(SyncHistory.outcome, func.count(SyncHistory.id))
                .filter(SyncHistory.profile_name == profile)
                .group_by(SyncHistory.outcome)
                .all()
            )
            stats = {str(outcome): count for outcome, count in stats_rows}
            logger.debug(f"Stats for profile {profile}: {stats}")
            return stats

    async def get_page(
        self,
        profile: str,
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=250),
        outcome: str | None = None,
        include_library_media: bool = True,
        include_list_media: bool = True,
    ) -> HistoryPage:
        """Return paginated history entries enriched as requested.

        Args:
            profile (str): The profile name to filter history entries.
            page (int): The page number to retrieve.
            per_page (int): The number of entries per page.
            outcome (str | None): Optional filter for the sync outcome.
            include_library_media (bool): Include library provider metadata when True.
            include_list_media (bool): Include list provider metadata when True.

        Returns:
            HistoryPage: The paginated history entries.

        Raises:
            SchedulerNotInitializedError: If the scheduler is not running.
            ProfileNotFoundError: If the profile is unknown.
        """
        logger.debug(
            f"get_page(profile={profile}, page={page}, "
            f"per_page={per_page}, outcome={outcome}, include_list_media="
            f"{include_list_media}, include_library_media={include_library_media})"
        )

        base_filters = [SyncHistory.profile_name == profile]
        if outcome:
            base_filters.append(SyncHistory.outcome == outcome)

        with db() as ctx:
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
            list_pairs: dict[str, set[str]] = defaultdict(set)
            library_pairs: dict[tuple[str, str | None], set[str]] = defaultdict(set)
            for row in rows:
                if row.list_namespace and row.list_media_key:
                    list_pairs[row.list_namespace].add(row.list_media_key)
                if row.library_namespace and row.library_media_key:
                    library_pairs[(row.library_namespace, row.library_section_key)].add(
                        row.library_media_key
                    )

            pin_map: dict[tuple[str, str], list[str]] = {}
            if list_pairs:
                namespaces = list(list_pairs.keys())
                keys = {
                    key
                    for namespace in namespaces
                    for key in list_pairs.get(namespace, set())
                }
                if keys:
                    pin_rows = (
                        ctx.session.query(Pin)
                        .filter(
                            Pin.profile_name == profile,
                            Pin.list_namespace.in_(namespaces),
                            Pin.list_media_key.in_(list(keys)),
                        )
                        .all()
                    )
                    pin_map = {
                        (pin.list_namespace, pin.list_media_key): list(pin.fields or [])
                        for pin in pin_rows
                    }

        list_metadata_map: dict[tuple[str, str], ProviderMediaMetadata] = {}
        if include_list_media:
            for namespace, keys in list_pairs.items():
                if not keys:
                    continue
                metadata = await self._fetch_list_metadata_batch(
                    profile, namespace, tuple(sorted(keys))
                )
                for key, payload in metadata.items():
                    list_metadata_map[(namespace, key)] = payload

        library_metadata_map: dict[tuple[str, str], ProviderMediaMetadata] = {}
        if include_library_media:
            for (namespace, section_key), keys in library_pairs.items():
                if not keys:
                    continue
                metadata = await self._fetch_library_metadata_batch(
                    profile, namespace, section_key, tuple(sorted(keys))
                )
                for key, payload in metadata.items():
                    library_metadata_map[(namespace, key)] = payload

        dto_items: list[HistoryItem] = []
        for row in rows:
            list_metadata = None
            if row.list_namespace and row.list_media_key:
                list_metadata = list_metadata_map.get(
                    (row.list_namespace, row.list_media_key)
                )
            library_metadata = None
            if row.library_namespace and row.library_media_key:
                library_metadata = library_metadata_map.get(
                    (row.library_namespace, row.library_media_key)
                )

            dto_items.append(
                HistoryItem(
                    id=row.id,
                    profile_name=row.profile_name,
                    library_namespace=row.library_namespace,
                    library_section_key=row.library_section_key,
                    library_media_key=row.library_media_key,
                    list_namespace=row.list_namespace,
                    list_media_key=row.list_media_key,
                    media_kind=row.media_kind.value if row.media_kind else None,
                    outcome=str(row.outcome),
                    before_state=row.before_state,
                    after_state=row.after_state,
                    error_message=row.error_message,
                    timestamp=row.timestamp.isoformat(),
                    library_media=library_metadata,
                    list_media=list_metadata,
                    pinned_fields=(
                        pin_map.get((row.list_namespace, row.list_media_key))
                        if row.list_namespace and row.list_media_key
                        else None
                    ),
                )
            )

        page_obj = HistoryPage(
            items=dto_items,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page,
            stats=stats,
        )
        logger.debug(
            f"Returning {len(dto_items)} items (total={total}, pages={page_obj.pages})"
        )
        return page_obj

    async def delete_item(self, profile: str, item_id: int) -> None:
        """Delete a single history item for a profile.

        Args:
            profile (str): The profile name.
            item_id (int): The ID of the history item to delete.

        Raises:
            HistoryItemNotFoundError: If the item does not exist.
        """
        logger.info(f"Deleting history item id={item_id} for profile {profile}")
        with db() as ctx:
            row = (
                ctx.session.query(SyncHistory)
                .filter(SyncHistory.profile_name == profile, SyncHistory.id == item_id)
                .first()
            )
            if not row:
                raise HistoryItemNotFoundError("Not found")
            ctx.session.delete(row)
            ctx.session.commit()

        # Invalidate related caches after deletion
        await self.clear_profile_cache(profile)

    async def undo_item(self, profile: str, item_id: int) -> HistoryItem:
        """Undo a history item by reverting or deleting the AniList entry.

        Args:
            profile (str): Profile name
            item_id (int): History row id to undo

        Returns:
            HistoryItem: Newly created history record representing the undo action.

        Raises:
            SchedulerNotInitializedError: If the scheduler is not running.
            ProfileNotFoundError: If the profile is unknown.
            HistoryItemNotFoundError: If the specified item does not exist.
        """
        logger.info(f"Undoing history item id={item_id} for profile {profile}")
        bridge = self._get_bridge(profile)
        list_provider = bridge.list_provider

        with db() as ctx:
            row = (
                ctx.session.query(SyncHistory)
                .filter(SyncHistory.profile_name == profile, SyncHistory.id == item_id)
                .first()
            )
            if not row:
                raise HistoryItemNotFoundError("Not found")

        if not row.list_media_key:
            raise HistoryItemNotFoundError(
                "Cannot undo history item without list media key"
            )

        if not row.before_state:
            log.success(f"Deleting list entry {row.list_media_key} as part of undo")
            if bridge.profile_config.dry_run:
                log.info(
                    "Dry run enabled; skipping deletion of list entry "
                    f"{row.list_media_key}"
                )
            else:
                await list_provider.delete_entry(row.list_media_key)

        # TODO: Implement undo logic on provider side
        raise NotImplementedError(
            "Undo operations are not supported with the provider abstraction."
        )

    async def clear_profile_cache(self, profile: str) -> None:
        """Clear all cached data for a specific profile.

        Args:
            profile: Profile name to clear cache for
        """
        self._fetch_list_metadata_batch.cache_clear()
        self._fetch_library_metadata_batch.cache_clear()
        self._fetch_profile_stats.cache_clear()

    async def clear_all_caches(self) -> None:
        """Clear all caches."""
        self._fetch_list_metadata_batch.cache_clear()
        self._fetch_library_metadata_batch.cache_clear()
        self._fetch_profile_stats.cache_clear()

    def get_cache_info(self) -> dict[str, Any]:
        """Get cache statistics for monitoring.

        Returns:
            Dictionary with cache hit/miss statistics
        """
        return {
            "list_cache": self._fetch_list_metadata_batch.cache_info(),
            "library_cache": self._fetch_library_metadata_batch.cache_info(),
            "stats_cache": self._fetch_profile_stats.cache_info(),
        }


@lru_cache(maxsize=1)
def get_history_service() -> HistoryService:
    """Get the singleton HistoryService instance.

    Returns:
        HistoryService: The history service instance.
    """
    return HistoryService()
