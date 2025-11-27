"""Provider-agnostic base class for library/list synchronization."""

import contextlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from anibridge.library import ExternalId, LibraryMedia, LibraryProvider
from anibridge.list import ListEntry, ListProvider, ListStatus
from rapidfuzz import fuzz

from src import log
from src.config.database import db
from src.config.settings import SyncField
from src.core.sync.stats import (
    BatchUpdate,
    EntrySnapshot,
    ItemIdentifier,
    SyncOutcome,
    SyncStats,
)
from src.models.db.animap import AniMap
from src.models.db.pin import Pin
from src.utils.types import Comparable

if TYPE_CHECKING:
    from src.core.animap import AniMapClient

__all__ = ["BaseSyncClient"]


def diff_snapshots(
    before: EntrySnapshot | None,
    after: EntrySnapshot | None,
    fields: set[str],
) -> dict[str, tuple[Any, Any]]:
    """Compute differences between two snapshots for the specified fields."""
    diff: dict[str, tuple[Any, Any]] = {}
    before_map = before.to_dict() if before else {}
    after_map = after.to_dict() if after else {}
    for field in fields:
        if before_map.get(field) != after_map.get(field):
            diff[field] = (before_map.get(field), after_map.get(field))
    return diff


class BaseSyncClient[
    ParentMediaT: LibraryMedia,
    ChildMediaT: LibraryMedia,
    GrandchildMediaT: LibraryMedia,
](ABC):
    """Provider-agnostic base class for media synchronization."""

    _ENTRY_FIELD_MAP: ClassVar[dict[SyncField, str]] = {
        SyncField.STATUS: "status",
        SyncField.PROGRESS: "progress",
        SyncField.REPEATS: "repeats",
        SyncField.REVIEW: "review",
        SyncField.USER_RATING: "user_rating",
        SyncField.STARTED_AT: "started_at",
        SyncField.FINISHED_AT: "finished_at",
    }

    _COMPARISON_RULES: ClassVar[dict[SyncField, str]] = {
        SyncField.STATUS: "gte",
        SyncField.PROGRESS: "gt",
        SyncField.REPEATS: "gt",
        SyncField.REVIEW: "ne",
        SyncField.USER_RATING: "ne",
        SyncField.STARTED_AT: "lt",
        SyncField.FINISHED_AT: "lt",
    }

    def __init__(
        self,
        *,
        library_provider: LibraryProvider,
        list_provider: ListProvider,
        animap_client: AniMapClient,
        excluded_sync_fields: Sequence[SyncField],
        full_scan: bool,
        destructive_sync: bool,
        search_fallback_threshold: int,
        batch_requests: bool,
        dry_run: bool,
        profile_name: str,
    ) -> None:
        """Initialize the base synchronisation client."""
        self.library_provider = library_provider
        self.list_provider = list_provider
        self.animap_client = animap_client
        self.excluded_sync_fields = {field.value for field in excluded_sync_fields}
        self.full_scan = full_scan
        self.destructive_sync = destructive_sync
        self.search_fallback_threshold = search_fallback_threshold
        self.batch_requests = batch_requests
        self.dry_run = dry_run
        self.profile_name = profile_name

        self.sync_stats = SyncStats()
        self._pin_cache: dict[tuple[str, str], list[str]] = {}
        self._batch_entries: list[ListEntry] = []
        self.batch_history_items: list[BatchUpdate[ParentMediaT, ChildMediaT]] = []

        self._field_calculators: dict[
            SyncField,
            Callable[..., Any],
        ] = {
            SyncField.STATUS: self._calculate_status,
            SyncField.PROGRESS: self._calculate_progress,
            SyncField.REPEATS: self._calculate_repeats,
            SyncField.REVIEW: self._calculate_review,
            SyncField.USER_RATING: self._calculate_user_rating,
            SyncField.STARTED_AT: self._calculate_started_at,
            SyncField.FINISHED_AT: self._calculate_finished_at,
        }

    def clear_cache(self) -> None:
        """Clear any LRU/TTL caches defined on the client."""
        for attr in dir(self):
            value = getattr(self, attr, None)
            if callable(value) and hasattr(value, "cache_clear"):
                value.cache_clear()  # type: ignore
        self._pin_cache.clear()

    def _get_pinned_fields(self, namespace: str, media_key: str | None) -> list[str]:
        """Return the set of pinned fields for the given list media identifier."""
        if not media_key:
            return []

        cache_key = (namespace, media_key)
        cached = self._pin_cache.get(cache_key)
        if cached is not None:
            return cached

        with db() as ctx:
            pin: Pin | None = (
                ctx.session.query(Pin)
                .filter(
                    Pin.profile_name == self.profile_name,
                    Pin.list_namespace == namespace,
                    Pin.list_media_key == media_key,
                )
                .first()
            )

        fields = list(pin.fields) if pin and pin.fields else []
        self._pin_cache[cache_key] = fields
        return fields

    async def process_media(self, item: ParentMediaT) -> None:
        """Process a single library item."""
        ids_summary = self._format_external_ids(item.ids())
        log.debug(
            f"[{self.profile_name}] Processing {item.media_kind.value} "
            f"$$'{item.title}'$$ {ids_summary}"
        )

        item_identifier = ItemIdentifier.from_item(item)
        trackable = await self._get_all_trackable_items(item)
        if trackable:
            self.sync_stats.register_pending_items(trackable)
            self.sync_stats.track_item(item_identifier, SyncOutcome.PENDING)
        else:
            log.debug(
                f"[{self.profile_name}] Skipping {item.media_kind.value} "
                f"$$'{item.title}'$$ because it has no eligible items {ids_summary}"
            )
            self.sync_stats.track_item(item_identifier, SyncOutcome.SKIPPED)
            return

        found_match = False
        async for child_item, grandchild_items, animapping, entry in self.map_media(
            item
        ):
            found_match = True
            grandchildren = tuple(grandchild_items)
            grandchild_ids = ItemIdentifier.from_items(grandchildren)

            debug_ids = self._debug_log_ids(
                item=item, child_item=child_item, entry=entry, animapping=animapping
            )
            if entry is None:
                log.debug(
                    f"[{self.profile_name}] No existing list entry for "
                    f"{item.media_kind.value}; preparing new entry {debug_ids}"
                )
            else:
                log.debug(
                    f"[{self.profile_name}] Found list entry for "
                    f"{item.media_kind.value} {debug_ids}"
                )

            try:
                outcome = await self.sync_media(
                    item=item,
                    child_item=child_item,
                    grandchild_items=grandchildren,
                    entry=entry,
                    animapping=animapping,
                )
                self.sync_stats.track_items(grandchild_ids, outcome)
                self.sync_stats.track_item(item_identifier, outcome)
            except Exception:
                log.error(
                    f"[{self.profile_name}] Failed to process {item.media_kind.value} "
                    f"{debug_ids}",
                    exc_info=True,
                )
                self.sync_stats.track_items(grandchild_ids, SyncOutcome.FAILED)
                self.sync_stats.track_item(item_identifier, SyncOutcome.FAILED)

        if not found_match:
            await self._create_sync_history(
                item=item,
                child_item=None,
                grandchild_items=None,
                snapshots=(None, None),
                animapping=None,
                outcome=SyncOutcome.NOT_FOUND,
            )
            self.sync_stats.track_item(item_identifier, SyncOutcome.NOT_FOUND)

    @abstractmethod
    async def _get_all_trackable_items(
        self, item: ParentMediaT
    ) -> list[ItemIdentifier]:
        """Return all identifiers that should be tracked for the given item."""

    @abstractmethod
    def map_media(
        self, item: ParentMediaT
    ) -> AsyncIterator[
        tuple[
            ChildMediaT,
            Sequence[GrandchildMediaT],
            AniMap | None,
            ListEntry | None,
        ]
    ]:
        """Yield potential list entries matching the supplied library item."""

    @abstractmethod
    async def search_media(
        self, item: ParentMediaT, child_item: ChildMediaT
    ) -> ListEntry | None:
        """Search the list provider for fallback matches."""

    def _best_search_result(
        self, title: str, results: Sequence[ListEntry]
    ) -> ListEntry | None:
        """Return the best fuzzy match for the given title."""
        best_entry: ListEntry | None = None
        best_ratio = 0
        for entry in results:
            candidates = {entry.title}
            media_title = entry.media().title
            if media_title:
                candidates.add(media_title)
            for candidate in candidates:
                if not candidate:
                    continue
                ratio = fuzz.ratio(title, candidate)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_entry = entry
        if best_ratio < self.search_fallback_threshold:
            return None
        return best_entry

    async def sync_media(
        self,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry | None,
        animapping: AniMap | None,
    ) -> SyncOutcome:
        """Synchronize a mapped media item with the list provider."""
        entry_missing = entry is None
        entry = await self._ensure_entry(
            item=item,
            child_item=child_item,
            grandchild_items=grandchild_items,
            entry=entry,
            animapping=animapping,
        )

        debug_title = self._debug_log_title(item=item, animapping=animapping)
        debug_ids = self._debug_log_ids(
            item=item, child_item=child_item, entry=entry, animapping=animapping
        )

        if entry_missing:
            log.debug(
                f"[{self.profile_name}] Prepared new list entry for "
                f"{item.media_kind.value} {debug_title} {debug_ids}"
            )

        before_snapshot = EntrySnapshot.from_entry(entry)
        list_media_key = self._resolve_list_media_key(
            animapping, before_snapshot.media_key
        )
        pinned_fields = self._get_pinned_fields(
            self.list_provider.NAMESPACE, list_media_key
        )
        skip_fields = set(self.excluded_sync_fields) | set(pinned_fields)

        calc_kwargs = {
            "item": item,
            "child_item": child_item,
            "grandchild_items": grandchild_items,
            "entry": entry,
            "animapping": animapping,
        }

        status_value: ListStatus | None = await self._field_calculators[
            SyncField.STATUS
        ](**calc_kwargs)

        if status_value is None:
            if (
                self.destructive_sync
                and before_snapshot.status is not None
                and SyncField.STATUS.value not in skip_fields
            ):
                log.success(
                    f"[{self.profile_name}] Deleting list entry for "
                    f"{item.media_kind.value} {debug_title} {debug_ids}"
                )
                if self.dry_run:
                    log.info(
                        f"[{self.profile_name}] Dry run enabled; skipping deletion of "
                        f"{item.media_kind.value} {debug_title} {debug_ids}"
                    )
                    return SyncOutcome.SKIPPED
                else:
                    await self.list_provider.delete_entry(before_snapshot.media_key)

                await self._create_sync_history(
                    item=item,
                    child_item=child_item,
                    grandchild_items=grandchild_items,
                    snapshots=(before_snapshot, None),
                    animapping=animapping,
                    outcome=SyncOutcome.DELETED,
                )
                return SyncOutcome.DELETED

            log.info(
                f"[{self.profile_name}] Skipping {item.media_kind.value} "
                f"due to no activity {debug_title} {debug_ids}"
            )
            return SyncOutcome.SKIPPED

        considered_attrs: set[str] = set()

        if SyncField.STATUS.value not in skip_fields and self._should_update_field(
            self._COMPARISON_RULES[SyncField.STATUS],
            SyncField.STATUS.value,
            skip_fields,
            status_value,
            before_snapshot.status,
        ):
            entry.status = status_value
        considered_attrs.add(self._ENTRY_FIELD_MAP[SyncField.STATUS])
        final_status = entry.status

        for field in (
            SyncField.PROGRESS,
            SyncField.REPEATS,
            SyncField.REVIEW,
            SyncField.USER_RATING,
            SyncField.STARTED_AT,
            SyncField.FINISHED_AT,
        ):
            attr_name = self._ENTRY_FIELD_MAP[field]
            if field.value in skip_fields:
                continue
            if final_status is None:
                continue
            if (
                field
                in (SyncField.USER_RATING, SyncField.REPEATS, SyncField.FINISHED_AT)
                and final_status < ListStatus.COMPLETED
            ):
                continue
            if field is SyncField.STARTED_AT and final_status <= ListStatus.PLANNING:
                continue

            value = await self._field_calculators[field](**calc_kwargs)
            current_value = getattr(entry, attr_name)
            if not self._should_update_field(
                self._COMPARISON_RULES[field],
                field.value,
                skip_fields,
                value,
                current_value,
            ):
                continue

            setattr(entry, attr_name, value)
            considered_attrs.add(attr_name)

        after_snapshot = EntrySnapshot.from_entry(entry)
        diff = diff_snapshots(before_snapshot, after_snapshot, considered_attrs)

        if not diff:
            log.info(
                f"[{self.profile_name}] Skipping {item.media_kind.value} "
                f"because it is already up to date {debug_title} {debug_ids}"
            )
            return SyncOutcome.SKIPPED

        diff_str = self._format_diff(diff)

        if self.batch_requests:
            log.info(
                f"[{self.profile_name}] Queuing {item.media_kind.value} "
                f"for batch sync {debug_title} {debug_ids}"
            )
            log.success(f"\t\tQUEUED UPDATE: {diff_str}")
            self._batch_entries.append(entry)
            self.batch_history_items.append(
                BatchUpdate(
                    item=item,
                    child=child_item,
                    grandchildren=grandchild_items,
                    mapping=animapping,
                    before=before_snapshot,
                    after=after_snapshot,
                    entry=entry,
                )
            )
            return SyncOutcome.SYNCED

        if self.dry_run:
            log.info(
                f"[{self.profile_name}] Dry run enabled; skipping sync of "
                f"{item.media_kind.value} {debug_title} {debug_ids}"
            )
            log.success(f"\t\tDRY RUN UPDATE: {diff_str}")
            return SyncOutcome.SKIPPED

        try:
            await self.list_provider.update_entry(after_snapshot.media_key, entry)
            log.success(
                f"[{self.profile_name}] Synced {item.media_kind.value} "
                f"{debug_title} {debug_ids}"
            )
            log.success(f"\t\tUPDATE: {diff_str}")
            await self._create_sync_history(
                item=item,
                child_item=child_item,
                grandchild_items=grandchild_items,
                snapshots=(before_snapshot, after_snapshot),
                animapping=animapping,
                outcome=SyncOutcome.SYNCED,
            )
            return SyncOutcome.SYNCED
        except Exception as exc:
            log.error(
                f"[{self.profile_name}] Failed to sync {item.media_kind.value} "
                f"{debug_title} {debug_ids}",
                exc_info=True,
            )
            await self._create_sync_history(
                item=item,
                child_item=child_item,
                grandchild_items=grandchild_items,
                snapshots=(before_snapshot, after_snapshot),
                animapping=animapping,
                outcome=SyncOutcome.FAILED,
                error_message=str(exc),
            )
            raise

    async def batch_sync(self) -> None:
        """Flush any queued batch updates to the list provider."""
        if not self._batch_entries:
            return

        log.success(
            f"[{self.profile_name}] Syncing {len(self._batch_entries)} items "
            f"to list provider in batch mode"
        )

        if self.dry_run:
            log.info(
                f"[{self.profile_name}] Dry run enabled; skipping batch sync of "
                f"{len(self._batch_entries)} items"
            )
            for record in self.batch_history_items:
                before_snapshot = record.before
                after_snapshot = record.after
                diff = diff_snapshots(
                    before_snapshot,
                    after_snapshot,
                    set(after_snapshot.to_dict().keys()),
                )
                diff_str = self._format_diff(diff)
                debug_title = self._debug_log_title(
                    item=record.item, animapping=record.mapping
                )
                debug_ids = self._debug_log_ids(
                    item=record.item,
                    child_item=record.child,
                    entry=record.entry,
                    animapping=record.mapping,
                )
                log.success(
                    f"[{self.profile_name}] Dry run update for "
                    f"{record.item.media_kind.value} {debug_title} {debug_ids}"
                )
                log.success(f"\t\tDRY RUN BATCH UPDATE: {diff_str}")
            self._batch_entries.clear()
            self.batch_history_items.clear()
            return

        try:
            await self.list_provider.update_entries_batch(self._batch_entries)
            for record in self.batch_history_items:
                await self._create_sync_history(
                    item=record.item,
                    child_item=record.child,
                    grandchild_items=record.grandchildren,
                    snapshots=(record.before, record.after),
                    animapping=record.mapping,
                    outcome=SyncOutcome.SYNCED,
                )
        except Exception as exc:
            log.error("Batch sync failed", exc_info=True)
            for record in self.batch_history_items:
                await self._create_sync_history(
                    item=record.item,
                    child_item=record.child,
                    grandchild_items=record.grandchildren,
                    snapshots=(record.before, record.after),
                    animapping=record.mapping,
                    outcome=SyncOutcome.FAILED,
                    error_message=str(exc),
                )
            raise
        finally:
            self._batch_entries.clear()
            self.batch_history_items.clear()

    async def _create_sync_history(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT | None,
        grandchild_items: Sequence[LibraryMedia] | None,
        snapshots: tuple[EntrySnapshot | None, EntrySnapshot | None],
        animapping: AniMap | None,
        outcome: SyncOutcome,
        error_message: str | None = None,
    ) -> None:
        """Record the outcome of a sync attempt."""
        from src.models.db.sync_history import SyncHistory

        before_snapshot, after_snapshot = snapshots
        before_state = before_snapshot.serialize() if before_snapshot else None
        after_state = after_snapshot.serialize() if after_snapshot else None

        resolved_media_key = (
            after_snapshot.media_key
            if after_snapshot
            else before_snapshot.media_key
            if before_snapshot
            else None
        )
        list_media_key = self._resolve_list_media_key(animapping, resolved_media_key)

        library_target: LibraryMedia = child_item if child_item is not None else item
        library_media_key = str(library_target.key)
        library_namespace = self.library_provider.NAMESPACE
        list_namespace = self.list_provider.NAMESPACE
        media_kind = library_target.media_kind

        library_section_key: str | None = None
        try:
            section = library_target.section()
            library_section_key = section.key
        except Exception:
            library_section_key = None

        with db() as ctx:
            if outcome == SyncOutcome.SYNCED:
                delete_filters = [
                    SyncHistory.profile_name == self.profile_name,
                    SyncHistory.library_section_key == library_section_key,
                    SyncHistory.library_namespace == library_namespace,
                    SyncHistory.library_media_key == library_media_key,
                    SyncHistory.outcome.in_(
                        [SyncOutcome.NOT_FOUND, SyncOutcome.FAILED]
                    ),
                ]
                if list_media_key is not None:
                    delete_filters.extend(
                        [
                            SyncHistory.list_namespace == list_namespace,
                            SyncHistory.list_media_key == list_media_key,
                        ]
                    )
                ctx.session.query(SyncHistory).filter(*delete_filters).delete(
                    synchronize_session=False
                )

            if outcome == SyncOutcome.SKIPPED:
                return

            if outcome in (SyncOutcome.NOT_FOUND, SyncOutcome.FAILED):
                filters = [
                    SyncHistory.profile_name == self.profile_name,
                    SyncHistory.library_namespace == library_namespace,
                    SyncHistory.library_media_key == library_media_key,
                    SyncHistory.outcome == outcome,
                ]
                if list_media_key is None:
                    filters.append(SyncHistory.list_media_key.is_(None))
                else:
                    filters.extend(
                        [
                            SyncHistory.list_namespace == list_namespace,
                            SyncHistory.list_media_key == list_media_key,
                        ]
                    )
                existing = ctx.session.query(SyncHistory).filter(*filters).first()
                if existing:
                    if existing.error_message == error_message:
                        return
                    existing.before_state = before_state
                    existing.after_state = after_state
                    existing.error_message = error_message
                    existing.timestamp = datetime.now(UTC)
                    ctx.session.commit()
                    return

            history_record = SyncHistory(
                profile_name=self.profile_name,
                library_namespace=library_namespace,
                library_section_key=library_section_key,
                library_media_key=library_media_key,
                list_namespace=list_namespace,
                list_media_key=list_media_key,
                media_kind=media_kind,
                outcome=outcome,
                before_state=before_state,
                after_state=after_state,
                error_message=error_message,
            )
            ctx.session.add(history_record)
            ctx.session.commit()

    def _resolve_list_media_key(
        self, animapping: AniMap | None, media_key: str | None
    ) -> str | None:
        """Resolve the list provider media identifier for logging/history."""
        if animapping and animapping.anilist_id:
            return str(animapping.anilist_id)
        if media_key is None:
            return None
        return str(media_key)

    def _should_update_field(
        self,
        op: str,
        field_name: str,
        skip_fields: set[str],
        new_value: Comparable | None,
        current_value: Comparable | None,
    ) -> bool:
        """Determine whether a field should be updated."""
        if field_name in skip_fields:
            return False
        if self.destructive_sync and new_value is not None:
            return True
        if current_value == new_value:
            return False
        if current_value is None:
            return new_value is not None
        if new_value is None:
            return False

        match op:
            case "ne":
                return new_value != current_value
            case "gt":
                return new_value > current_value
            case "gte":
                return new_value >= current_value
            case "lt":
                return new_value < current_value
            case "lte":
                return new_value <= current_value
        return False

    def _extract_external_ids(
        self, item: LibraryMedia
    ) -> tuple[list[str], list[int], list[int], list[int], list[int], list[int]]:
        """Extract external IDs from a library media item."""
        anidb_ids: list[int] = []
        anilist_ids: list[int] = []
        imdb_ids: list[str] = []
        mal_ids: list[int] = []
        tmdb_ids: list[int] = []
        tvdb_ids: list[int] = []

        for external in item.ids():
            match external.namespace:
                case "imdb":
                    imdb_ids.append(external.value)
                case "tmdb":
                    with contextlib.suppress(ValueError):
                        tmdb_ids.append(int(external.value))
                case "tvdb":
                    with contextlib.suppress(ValueError):
                        tvdb_ids.append(int(external.value))
                case "anidb":
                    with contextlib.suppress(ValueError):
                        anidb_ids.append(int(external.value))
                case "mal":
                    with contextlib.suppress(ValueError):
                        mal_ids.append(int(external.value))
                case "anilist":
                    with contextlib.suppress(ValueError):
                        anilist_ids.append(int(external.value))
                case _:
                    continue

        return imdb_ids, tmdb_ids, tvdb_ids, anidb_ids, anilist_ids, mal_ids

    def _format_external_ids(self, ids: Sequence[ExternalId]) -> str:
        """Format external identifiers for debug logging."""
        if not ids:
            return "$${}$$"
        formatted = ", ".join(repr(external) for external in ids)
        return f"$${{{formatted}}}$$"

    def _format_diff(self, diff: dict[str, tuple[Any, Any]]) -> str:
        """Format a diff dictionary for logging."""
        parts: list[str] = []
        for field, (before, after) in diff.items():
            parts.append(
                f"{field}: {self._format_value(before)} -> {self._format_value(after)}"
            )
        return ", ".join(parts)

    @staticmethod
    def _format_value(value: Any) -> str:
        """Format individual values for diff logging."""
        if isinstance(value, ListStatus):
            return value.value
        if isinstance(value, datetime):
            dt = value
            dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
            return dt.isoformat()
        if value is None:
            return "None"
        return repr(value)

    @abstractmethod
    async def _calculate_status(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> ListStatus | None:
        """Calculate the desired status for the list entry."""

    @abstractmethod
    async def _calculate_user_rating(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        """Calculate the desired score for the list entry."""

    @abstractmethod
    async def _calculate_progress(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        """Calculate the desired progress for the list entry."""

    @abstractmethod
    async def _calculate_repeats(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> int | None:
        """Calculate the desired repeat count for the list entry."""

    @abstractmethod
    async def _calculate_started_at(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> datetime | None:
        """Calculate the desired start date for the list entry."""

    @abstractmethod
    async def _calculate_finished_at(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> datetime | None:
        """Calculate the desired completion date for the list entry."""

    @abstractmethod
    async def _calculate_review(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry,
        animapping: AniMap | None,
    ) -> str | None:
        """Calculate the desired review/notes for the list entry."""

    @abstractmethod
    def _debug_log_title(
        self, item: ParentMediaT, animapping: AniMap | None = None
    ) -> str:
        """Return a debug-friendly title representation."""

    @abstractmethod
    def _debug_log_ids(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        entry: ListEntry | None,
        animapping: AniMap | None,
    ) -> str:
        """Return a debug-friendly identifier representation."""

    async def _ensure_entry(
        self,
        *,
        item: ParentMediaT,
        child_item: ChildMediaT,
        grandchild_items: Sequence[GrandchildMediaT],
        entry: ListEntry | None,
        animapping: AniMap | None,
    ) -> ListEntry:
        """Materialize a list entry for synchronization, constructing when missing."""
        if entry is not None:
            return entry

        list_media_key = self._resolve_list_media_key(animapping, None)
        if list_media_key is None:
            raise ValueError(
                f"Unable to determine list media key for {item.media_kind.value} "
                f"{self._debug_log_title(item=item, animapping=animapping)}"
            )

        return await self.list_provider.build_entry(list_media_key)
