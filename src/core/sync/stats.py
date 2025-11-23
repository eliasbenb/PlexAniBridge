"""Synchronization statistics and tracking module."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from anibridge_providers.library import (
    LibraryEpisode,
    LibraryMedia,
    LibrarySeason,
    MediaKind,
)
from pydantic import BaseModel

from src.exceptions import UnsupportedMediaTypeError
from src.models.db.animap import AniMap

if TYPE_CHECKING:
    from anibridge_providers.list import ListEntry, ListStatus

__all__ = [
    "BatchUpdate",
    "EntrySnapshot",
    "ItemIdentifier",
    "SyncOutcome",
    "SyncProgress",
    "SyncStats",
]


class ItemIdentifier(BaseModel):
    """Immutable identifier for media items in sync operations.

    Provides a stable, hashable way to identify media items across
    the sync process without relying on fragile string representations.
    """

    rating_key: str
    title: str
    item_type: str  # 'movie', 'show', 'season', 'episode'
    parent_title: str | None = None
    season_index: int | None = None
    episode_index: int | None = None
    repr: str | None = None  # Cached string representation

    @classmethod
    def from_item(cls, item: LibraryMedia) -> ItemIdentifier:
        """Create an identifier from a library media entity."""
        kwargs = {
            "rating_key": str(item.key),
            "title": item.title,
            "item_type": item.media_kind.value,
            "parent_title": None,
            "season_index": None,
            "episode_index": None,
            "repr": repr(item),
        }

        if isinstance(item, LibraryEpisode):
            show = item.show()
            kwargs["parent_title"] = show.title if show else None
            kwargs["season_index"] = item.season_index
            kwargs["episode_index"] = item.index
        elif isinstance(item, LibrarySeason):
            show = item.show()
            kwargs["parent_title"] = show.title if show else None
            kwargs["season_index"] = item.index
        elif item.media_kind in (MediaKind.MOVIE, MediaKind.SHOW):
            # No additional metadata required for top-level movie/show types
            pass
        else:
            raise UnsupportedMediaTypeError(f"Unsupported media type: {type(item)}")

        return cls(**kwargs)

    @classmethod
    def from_items(cls, items: Sequence[LibraryMedia]) -> Sequence[ItemIdentifier]:
        """Create ItemIdentifiers from a list of Plex media objects.

        Args:
            items (Sequence[LibraryMedia]): List of library media objects

        Returns:
            Sequence[ItemIdentifier]: List of identifiers for the media items
        """
        return [cls.from_item(item) for item in items]

    def __hash__(self) -> int:
        """Generate a hash for the ItemIdentifier instance.

        Returns:
            int: Hash value of the instance
        """
        return hash((self.rating_key, self.item_type))

    def __repr__(self) -> str:
        """Generate a string representation of the ItemIdentifier instance.

        Returns:
            str: String representation of the instance
        """
        if self.repr:
            return self.repr
        return super().__repr__()


class SyncOutcome(StrEnum):
    """Enumeration of possible synchronization outcomes for media items."""

    SYNCED = "synced"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_FOUND = "not_found"
    DELETED = "deleted"
    PENDING = "pending"
    UNDONE = "undone"


class SyncStats(BaseModel):
    """Enhanced statistics tracker for synchronization operations.

    Uses an outcome-based approach where each item is tracked with its specific
    result, allowing for accurate reporting and easier debugging.
    """

    _item_outcomes: dict[ItemIdentifier, SyncOutcome] = {}

    def track_item(self, item_id: ItemIdentifier, outcome: SyncOutcome) -> None:
        """Track the outcome for a specific item.

        Args:
            item_id (ItemIdentifier): Identifier for the media item
            outcome (SyncOutcome): The synchronization outcome for this item
        """
        self._item_outcomes[item_id] = outcome

    def track_items(
        self, item_ids: Sequence[ItemIdentifier], outcome: SyncOutcome
    ) -> None:
        """Track the same outcome for multiple items.

        Args:
            item_ids (list[ItemIdentifier]): List of item identifiers
            outcome (SyncOutcome): The synchronization outcome for these items
        """
        for item_id in item_ids:
            self.track_item(item_id, outcome)

    def untrack_item(self, item_id: ItemIdentifier) -> None:
        """Remove an item from tracking.

        This is useful if an item was registered but later determined to be
        irrelevant or not part of the sync process.

        Args:
            item_id (ItemIdentifier): Identifier for the media item to untrack
        """
        if item_id in self._item_outcomes:
            del self._item_outcomes[item_id]

    def untrack_items(self, item_ids: Sequence[ItemIdentifier]) -> None:
        """Remove multiple items from tracking.

        Args:
            item_ids (Sequence[ItemIdentifier]): List of item identifiers to untrack
        """
        for item_id in item_ids:
            self.untrack_item(item_id)

    def register_pending_items(self, item_ids: list[ItemIdentifier]) -> None:
        """Register items as pending processing.

        This should be called at the start of processing to ensure all items
        that should be processed are tracked.

        Args:
            item_ids (list[ItemIdentifier]): List of item identifiers to register
        """
        for item_id in item_ids:
            if item_id not in self._item_outcomes:
                self._item_outcomes[item_id] = SyncOutcome.PENDING

    def get_items_by_outcome(self, *outcomes: SyncOutcome) -> list[ItemIdentifier]:
        """Get all items that had a specific outcome.

        Args:
            outcomes (SyncOutcome): One or more outcomes to filter by

        Returns:
            list[ItemIdentifier]: Items with the specified outcome(s)
        """
        if not outcomes:
            return [
                item_id
                for item_id in self._item_outcomes
                if item_id.item_type in ("show", "movie")
            ]
        return [
            item_id
            for item_id, item_outcome in self._item_outcomes.items()
            if item_outcome in outcomes and item_id.item_type in ("show", "movie")
        ]

    def get_grandchild_items_by_outcome(
        self, *outcome: SyncOutcome
    ) -> list[ItemIdentifier]:
        """Get all grandchild items (episodes/movies) that had a specific outcome.

        Args:
            outcome (SyncOutcome): One or more outcomes to filter by

        Returns:
            list[ItemIdentifier]: Grandchild items with the specified outcome(s)
        """
        if not outcome:
            return [
                item_id
                for item_id in self._item_outcomes
                if item_id.item_type in ("episode", "movie")
            ]
        return [
            item_id
            for item_id, item_outcome in self._item_outcomes.items()
            if item_outcome in outcome and item_id.item_type in ("episode", "movie")
        ]

    @property
    def synced(self) -> int:
        """Number of successfully synced items (including deleted)."""
        return len(self.get_items_by_outcome(SyncOutcome.SYNCED))

    @property
    def deleted(self) -> int:
        """Number of items deleted from AniList."""
        return len(self.get_items_by_outcome(SyncOutcome.DELETED))

    @property
    def skipped(self) -> int:
        """Number of items skipped (no changes needed)."""
        return len(self.get_items_by_outcome(SyncOutcome.SKIPPED))

    @property
    def not_found(self) -> int:
        """Number of items where no matching AniList entry was found."""
        return len(self.get_items_by_outcome(SyncOutcome.NOT_FOUND))

    @property
    def failed(self) -> int:
        """Number of items that failed to process."""
        return len(self.get_items_by_outcome(SyncOutcome.FAILED))

    @property
    def pending(self) -> int:
        """Number of items that are still pending processing."""
        return len(self.get_items_by_outcome(SyncOutcome.PENDING))

    @property
    def total_processed(self) -> int:
        """Total number of items processed (excluding pending)."""
        return len(
            self.get_items_by_outcome(
                SyncOutcome.SYNCED,
                SyncOutcome.SKIPPED,
                SyncOutcome.FAILED,
                SyncOutcome.NOT_FOUND,
                SyncOutcome.DELETED,
            )
        )

    @property
    def total_items(self) -> int:
        """Total number of items tracked (including unprocessed)."""
        return len(self.get_items_by_outcome())

    @property
    def coverage(self) -> float:
        """Percentage of grandchild items that were successfully processed."""
        total = len(self.get_grandchild_items_by_outcome())
        if not total:
            return 1.0

        processed = len(
            self.get_grandchild_items_by_outcome(
                SyncOutcome.SYNCED,
                SyncOutcome.SKIPPED,
                SyncOutcome.FAILED,
                SyncOutcome.NOT_FOUND,
                SyncOutcome.DELETED,
            )
        )

        return processed / total

    def combine(self, other: SyncStats) -> SyncStats:
        """Combine this stats instance with another.

        Args:
            other (SyncStats): Another SyncStats instance to combine with

        Returns:
            SyncStats: New instance with combined statistics
        """
        combined = SyncStats()
        combined._item_outcomes = {**self._item_outcomes, **other._item_outcomes}
        return combined

    def __add__(self, other: SyncStats) -> SyncStats:
        """Combine statistics using the + operator."""
        return self.combine(other)


class SyncProgress(BaseModel):
    """Live sync progress snapshot exposed to the web UI.

    Fields are serialized to JSON in scheduler status responses.
    """

    state: Literal["running", "idle"]
    started_at: datetime
    section_index: int
    section_count: int
    section_title: str | None
    stage: str
    section_items_total: int
    section_items_processed: int


@dataclass(slots=True)
class EntrySnapshot:
    """Snapshot of list entry fields used for comparison and history."""

    media_key: str
    status: ListStatus | None
    progress: int | None
    repeats: int | None
    review: str | None
    user_rating: int | None
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_entry(cls, entry: ListEntry) -> EntrySnapshot:
        """Create a snapshot from a list entry."""
        return cls(
            media_key=entry.media().key,
            status=entry.status,
            progress=entry.progress,
            repeats=entry.repeats,
            review=entry.review,
            user_rating=entry.user_rating,
            started_at=entry.started_at,
            finished_at=entry.finished_at,
        )

    def asdict(self) -> dict[str, Any]:
        """Return a raw dictionary representation."""
        return {
            "media_key": self.media_key,
            "status": self.status,
            "progress": self.progress,
            "repeats": self.repeats,
            "review": self.review,
            "user_rating": self.user_rating,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def serialize(self) -> dict[str, Any]:
        """Serialize values into JSON-friendly primitives."""

        def _serialize(value: Any) -> Any:
            if isinstance(value, datetime):
                dt = value
                dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
                return dt.isoformat()
            if isinstance(value, ListStatus):
                return value.value
            return value

        return {key: _serialize(value) for key, value in self.asdict().items()}


@dataclass(slots=True)
class BatchUpdate[ParentMediaT: LibraryMedia, ChildMediaT: LibraryMedia]:
    """Container for deferred batch updates and associated metadata."""

    item: ParentMediaT
    child: ChildMediaT
    grandchildren: Sequence[LibraryMedia]
    mapping: AniMap | None
    before: EntrySnapshot | None
    after: EntrySnapshot
    entry: ListEntry
