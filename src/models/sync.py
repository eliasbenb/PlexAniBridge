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


class ItemIdentifier(BaseModel):
    """Immutable identifier for media items in sync operations.

    Provides a stable, hashable way to identify media items across
    the sync process without relying on fragile string representations.
    """

    rating_key: str
    title: str
    item_type: str  # 'movie', 'show', 'season', 'episode'
    parent_title: str | None = None  # For episodes/seasons
    season_index: int | None = None  # For episodes
    episode_index: int | None = None  # For episodes

    @classmethod
    def from_media(cls, item: Movie | Show | Season | Episode) -> "ItemIdentifier":
        """Create an ItemIdentifier from a Plex media object.

        Args:
            item: Plex media object (Movie, Show, Season, or Episode)

        Returns:
            ItemIdentifier: New identifier for the media item
        """
        if isinstance(item, Movie):
            return cls(
                rating_key=str(item.ratingKey), title=item.title, item_type="movie"
            )
        elif isinstance(item, Show):
            return cls(
                rating_key=str(item.ratingKey), title=item.title, item_type="show"
            )
        elif isinstance(item, Season):
            return cls(
                rating_key=str(item.ratingKey),
                title=item.title,
                item_type="season",
                parent_title=item.parentTitle,
                season_index=item.index,
            )
        elif isinstance(item, Episode):
            return cls(
                rating_key=str(item.ratingKey),
                title=item.title,
                item_type="episode",
                parent_title=item.grandparentTitle,
                season_index=item.parentIndex,
                episode_index=item.index,
            )
        else:
            raise ValueError(f"Unsupported media type: {type(item)}")

    @classmethod
    def from_items(cls, items: list[Movie] | list[Episode]) -> list["ItemIdentifier"]:
        """Create ItemIdentifiers from a list of Plex media objects.

        Args:
            items: List of Plex media objects

        Returns:
            list[ItemIdentifier]: List of identifiers for the media items
        """
        return [cls.from_media(item) for item in items]

    def __hash__(self) -> int:
        """Generate a hash for the ItemIdentifier instance.

        Returns:
            int: Hash value of the instance
        """
        return hash((self.rating_key, self.item_type))

    def __str__(self) -> str:
        """Generate a string representation of the ItemIdentifier.

        Returns:
            str: String representation in format 'ItemType: Title (RatingKey)'
        """
        if self.item_type == "episode":
            return (
                f"{self.parent_title} S{self.season_index:02d}E"
                f"{self.episode_index:02d} - {self.title}"
            )
        elif self.item_type == "season":
            return f"{self.parent_title} - Season {self.season_index}"
        else:
            return self.title


class SyncStats(BaseModel):
    """Enhanced statistics tracker for synchronization operations.

    Uses an outcome-based approach where each item is tracked with its specific
    result, allowing for accurate reporting and easier debugging.
    """

    _item_outcomes: dict[ItemIdentifier, SyncOutcome] = {}

    def track_item(self, item_id: ItemIdentifier, outcome: SyncOutcome) -> None:
        """Track the outcome for a specific item.

        Args:
            item_id: Identifier for the media item
            outcome: The synchronization outcome for this item
        """
        self._item_outcomes[item_id] = outcome

    def track_items(self, item_ids: list[ItemIdentifier], outcome: SyncOutcome) -> None:
        """Track the same outcome for multiple items.

        Args:
            item_ids: List of identifiers for media items
            outcome: The synchronization outcome for these items
        """
        for item_id in item_ids:
            self.track_item(item_id, outcome)

    def get_items_by_outcome(self, outcome: SyncOutcome) -> list[ItemIdentifier]:
        """Get all items that had a specific outcome.

        Args:
            outcome: The outcome to filter by

        Returns:
            list[ItemIdentifier]: Items with the specified outcome
        """
        return [
            item_id
            for item_id, item_outcome in self._item_outcomes.items()
            if item_outcome == outcome
        ]

    @property
    def synced(self) -> int:
        """Number of successfully synced items (including deleted)."""
        return len(
            [
                item
                for item, outcome in self._item_outcomes.items()
                if outcome in (SyncOutcome.SYNCED, SyncOutcome.DELETED)
            ]
        )

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
    def total_processed(self) -> int:
        """Total number of items processed."""
        return len(self._item_outcomes)

    @property
    def success_rate(self) -> float:
        """Percentage of items successfully processed (synced + skipped)."""
        if self.total_processed == 0:
            return 1.0
        successful = self.synced + self.skipped
        return successful / self.total_processed

    @property
    def coverage(self) -> float:
        """Alias for success_rate to maintain backward compatibility."""
        return self.success_rate

    def get_summary(self) -> dict[str, int]:
        """Get a summary of all outcomes.

        Returns:
            dict: Mapping of outcome names to counts
        """
        return {
            "synced": self.synced,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "not_found": self.not_found,
            "failed": self.failed,
            "total": self.total_processed,
        }

    def get_detailed_report(self) -> dict[str, list[str]]:
        """Get a detailed report showing which items had each outcome.

        Returns:
            dict: Mapping of outcome names to lists of item descriptions
        """
        return {
            outcome.value: [str(item) for item in self.get_items_by_outcome(outcome)]
            for outcome in SyncOutcome
        }

    def combine(self, other: "SyncStats") -> "SyncStats":
        """Combine this stats instance with another.

        Args:
            other: Another SyncStats instance to combine with

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
