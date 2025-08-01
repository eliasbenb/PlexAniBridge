"""Synchronization Models Module."""

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel

from plexapi.media import Guid
from plexapi.video import Episode, Movie, Season, Show


class SyncOutcome(StrEnum):
    """Enumeration of possible synchronization outcomes for media items."""

    SYNCED = "synced"  # Successfully synchronized to AniList
    SKIPPED = "skipped"  # Item already up to date, no changes needed
    FAILED = "failed"  # Failed to process due to error
    NOT_FOUND = "not_found"  # No matching AniList entry could be found
    DELETED = "deleted"  # Item was deleted from AniList (destructive sync)
    PENDING = "pending"  # Item was identified for processing but not yet processed


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
    def from_item(cls, item: Movie | Show | Season | Episode) -> "ItemIdentifier":
        """Create an ItemIdentifier from a Plex media object.

        Args:
            item (Movie | Show | Season | Episode): Plex media object

        Returns:
            ItemIdentifier: New identifier for the media item
        """
        kwargs = {
            "rating_key": str(item.ratingKey),
            "title": item.title,
            "item_type": item.type,
            "parent_title": None,
            "season_index": None,
            "episode_index": None,
            "repr": item.__repr__(),
        }

        if isinstance(item, Episode):
            kwargs["parent_title"] = item.grandparentTitle
            kwargs["season_index"] = item.parentIndex
            kwargs["episode_index"] = item.index
        elif isinstance(item, Season):
            kwargs["parent_title"] = item.parentTitle
            kwargs["season_index"] = item.index
        elif isinstance(item, Movie | Show):
            pass
        else:
            raise ValueError(f"Unsupported media type: {type(item)}")

        return cls(**kwargs)

    @classmethod
    def from_items(
        cls, items: list[Movie] | list[Show] | list[Season] | list[Episode]
    ) -> list["ItemIdentifier"]:
        """Create ItemIdentifiers from a list of Plex media objects.

        Args:
            items (list[Movie] | list[Show] | list[Season] | list[Episode]): List of
                Plex media objects

        Returns:
            list[ItemIdentifier]: List of identifiers for the media items
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

    def track_items(self, item_ids: list[ItemIdentifier], outcome: SyncOutcome) -> None:
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

    def untrack_items(self, item_ids: list[ItemIdentifier]) -> None:
        """Remove multiple items from tracking.

        Args:
            item_ids (list[ItemIdentifier]): List of item identifiers to untrack
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

    def combine(self, other: "SyncStats") -> "SyncStats":
        """Combine this stats instance with another.

        Args:
            other (SyncStats): Another SyncStats instance to combine with

        Returns:
            SyncStats: New instance with combined statistics
        """
        combined = SyncStats()
        combined._item_outcomes = {**self._item_outcomes, **other._item_outcomes}
        return combined

    def __add__(self, other: "SyncStats") -> "SyncStats":
        """Combine statistics using the + operator."""
        return self.combine(other)


class ParsedGuids(BaseModel):
    """Container for parsed media identifiers from different services.

    Handles parsing and storage of media IDs from various services (TVDB, TMDB, IMDB)
    from Plex's GUID format into a structured format. Provides iteration and string
    representation for debugging.

    Attributes:
        tvdb (int | None): TVDB ID if available
        tmdb (int | None): TMDB ID if available
        imdb (str | None): IMDB ID if available

    Note:
        GUID formats expected from Plex:
        - TVDB: "tvdb://123456"
        - TMDB: "tmdb://123456"
        - IMDB: "imdb://tt1234567"
    """

    tvdb: int | None = None
    tmdb: int | None = None
    imdb: str | None = None

    @staticmethod
    def from_guids(guids: list[Guid]) -> "ParsedGuids":
        """Creates a ParsedGuids instance from a list of Plex GUIDs.

        Args:
            guids (list[Guid]): List of Plex GUID objects

        Returns:
            ParsedGuids: New instance with parsed IDs
        """
        parsed_guids = ParsedGuids()
        for guid in guids:
            if not guid.id:
                continue

            split_guid = guid.id.split("://")
            if len(split_guid) != 2:
                continue

            attr = split_guid[0]
            if not hasattr(parsed_guids, attr):
                continue

            try:
                setattr(parsed_guids, attr, int(split_guid[1]))
            except ValueError:
                setattr(parsed_guids, attr, str(split_guid[1]))

        return parsed_guids

    def __str__(self) -> str:
        """Creates a string representation of the parsed IDs.

        Returns:
            str: String representation of the parsed IDs in a format like
                 "id: xxx, id: xxx, id: xxx"
        """
        return ", ".join(
            f"{field}: {getattr(self, field)}"
            for field in self.__class__.model_fields
            if getattr(self, field) is not None
        )


class Comparable(Protocol):
    """Protocol for objects that can be compared using <, >, <=, >= operators."""

    def __lt__(self, other: Any) -> bool:
        """Return True if this object is less than other."""
        ...

    def __gt__(self, other: Any) -> bool:
        """Return True if this object is greater than other."""
        ...

    def __le__(self, other: Any) -> bool:
        """Return True if this object is less than or equal to other."""
        ...

    def __ge__(self, other: Any) -> bool:
        """Return True if this object is greater than or equal to other."""
        ...
