"""List provider protocols for media libraries."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import total_ordering
from typing import Any, ClassVar, Protocol, runtime_checkable


class ListMediaType(StrEnum):
    """Supported media types in a list."""

    TV = "TV"
    MOVIE = "MOVIE"


@total_ordering
class ListStatus(StrEnum):
    """Supported statuses for media items in a list."""

    COMPLETED = "completed"
    CURRENT = "current"
    DROPPED = "dropped"
    PAUSED = "paused"
    PLANNING = "planning"
    REPEATING = "repeating"

    __PRIORITY: ClassVar[dict[str, int]] = {
        "completed": 3,
        "repeating": 3,
        "current": 2,
        "paused": 2,
        "dropped": 2,
        "planning": 1,
    }

    @property
    def priority(self) -> int:
        """Get the priority of the ListStatus for comparison purposes."""
        return self.__PRIORITY[self.value]

    def __lt__(self, other: object) -> bool:
        """Compare two ListStatus instances based on their priority."""
        if not isinstance(other, ListStatus):
            return NotImplemented
        return self.priority < other.priority

    def __eq__(self, other: object) -> bool:
        """Check equality of two ListStatus instances based on their priority."""
        if not isinstance(other, ListStatus):
            return NotImplemented
        return self.priority == other.priority


@dataclass(frozen=True, slots=True)
class ListUser:
    """User information for a media list."""

    key: str  # Any unique identifier for the user
    title: str

    def __hash__(self) -> int:
        """Compute the hash based on the user's key."""
        return hash(self.key)


@dataclass(frozen=True, slots=True)
class ProviderBackupEntries:
    """Parsed provider backup payload ready for restoration."""

    entries: Sequence[object]
    user: str | None = None


@runtime_checkable
class ListEntity(Protocol):
    """Base protocol for list entities."""

    key: str
    title: str

    def provider(self) -> ListProvider:
        """Get the list provider this entity belongs to.

        Returns:
            ListProvider: The list provider.
        """
        ...

    def __hash__(self) -> int:
        """Compute the hash based on the entity's key."""
        return hash(f"{self.provider().NAMESPACE}:{self.__class__.__name__}:{self.key}")

    def __repr__(self) -> str:
        """Return a string representation of the list entity."""
        return (
            f"<{self.__class__.__name__}:{self.provider().NAMESPACE}:{self.key}:"
            f"{self.title[:32]}>"
        )


@runtime_checkable
class ListMedia(ListEntity, Protocol):
    """Protocol for media items in a list."""

    @property
    def media_type(self) -> ListMediaType:
        """Get the type of media (e.g., TV, MOVIE)."""
        ...

    @property
    def total_units(self) -> int | None:
        """Return the total number of units (e.g. episodes) for the media."""
        ...


@runtime_checkable
class ListEntry(ListEntity, Protocol):
    """Base protocol for list entries."""

    @classmethod
    def create_empty(
        cls, provider: ListProvider, media: ListMedia | None = None
    ) -> ListEntry:
        """Create an empty list entry instance.

        Args:
            provider (ListProvider): The list provider for the entry.
            media (ListMedia | None): Optional media item for the entry.

        Returns:
            ListEntry: An empty list entry.
        """
        ...

    @property
    def progress(self) -> int | None:
        """Get the progress for the entry.

        Returns:
            int: The progress integer (e.g., episodes watched).
        """
        ...

    @progress.setter
    def progress(self, value: int | None) -> None:
        """Update the recorded progress for the entry."""
        ...

    @property
    def repeats(self) -> int | None:
        """Get the repeat count for the entry.

        If not available by the list provider, return 0.

        Returns:
            int: The number of times repeated.
        """
        ...

    @repeats.setter
    def repeats(self, value: int | None) -> None:
        """Update the repeat count for the entry."""
        ...

    @property
    def review(self) -> str | None:
        """Get the user's review for the entry.

        Returns:
            str | None: The user's review text, or None if not reviewed.
        """
        ...

    @review.setter
    def review(self, value: str | None) -> None:
        """Update the review for the entry."""
        ...

    @property
    def status(self) -> ListStatus | None:
        """Get the status of the entry in the list.

        Returns:
            ListStatus | None: The watch status.
        """
        ...

    @status.setter
    def status(self, value: ListStatus | None) -> None:
        """Update the status for the entry."""
        ...

    @property
    def user_rating(self) -> int | None:
        """Get the user rating for the list entry.

        Returns:
            int | None: The user rating on a 0-100 scale, or None if not rated.
        """
        ...

    @user_rating.setter
    def user_rating(self, value: int | None) -> None:
        """Update the user rating for the entry."""
        ...

    @property
    def started_at(self) -> datetime | None:
        """Get the timestamp when the user started watching the entry.

        Returns:
            datetime | None: The UTC timestamp when started, or None if not started.
        """
        ...

    @started_at.setter
    def started_at(self, value: datetime | None) -> None:
        """Update the timestamp when the user started the entry."""
        ...

    @property
    def finished_at(self) -> datetime | None:
        """Get the timestamp when the user finished watching the entry.

        This is the timestamp when the entry was completed for the *first* time.

        Returns:
            datetime | None: The UTC timestamp when finished, or None if not finished.
        """
        ...

    @finished_at.setter
    def finished_at(self, value: datetime | None) -> None:
        """Update the timestamp when the user finished the entry."""
        ...

    @property
    def total_units(self) -> int | None:
        """Return the total number of units (episodes/chapters) for the media."""
        ...

    def media(self) -> ListMedia:
        """Get the media item associated with the list entry.

        Returns:
            ListMedia: The media item.
        """
        ...


class ListProvider(Protocol):
    """Interface for a provider that exposes a user media list."""

    NAMESPACE: ClassVar[str]

    config: dict

    def __init__(self, *, config: dict | None = None) -> None:
        """Initialize the list provider.

        Args:
            config (dict | None): Optional configuration options for the provider.
        """
        self.config = config or {}

    async def initialize(self) -> None:
        """Perform any asynchronous startup work before the provider is used."""
        ...

    async def backup_list(self) -> str:
        """Backup the entire list from the provider.

        It is up to the implementation to decide the format of the backup data. Whatever
        format, it should be serializable/deserializable in string form.

        This is optional and may not be supported by all providers.

        Returns:
            str: A serialized string representation of all list entries.
        """
        raise NotImplementedError("List backup not implemented for this provider.")

    async def delete_entry(self, key: str) -> None:
        """Delete a list entry by its media key.

        Args:
            key (str): The unique key of the media item to delete.
        """
        ...

    async def get_entry(self, key: str) -> ListEntry | None:
        """Retrieve a list entry by its media key.

        Args:
            key (str): The unique key of the media item to retrieve.

        Returns:
            ListEntry | None: The list entry if found, otherwise None.
        """
        ...

    async def get_entries_batch(
        self, keys: Sequence[str]
    ) -> Sequence[ListEntry | None]:
        """Retrieve multiple list entries by their media keys.

        The order of the returned sequence must match the order of the input keys.

        Args:
            keys (Sequence[str]): The unique keys of the media items to retrieve.

        Returns:
            Sequence[ListEntry | None]: A sequence of list entries, with None for any
                not found.
        """
        entries: list[ListEntry | None] = []
        for key in keys:
            entry = await self.get_entry(key)
            entries.append(entry)
        return entries

    async def restore_list(self, backup: str) -> None:
        """Restore the list from a backup sequence of list entries.

        This is optional and may not be supported by all providers.

        Args:
            backup (str): The serialized string representation of the list entries.
        """
        raise NotImplementedError("List restore not implemented for this provider.")

    async def restore_entries(self, entries: Sequence[object]) -> None:
        """Restore a collection of list entries in bulk if supported."""
        raise NotImplementedError(
            "Entry restoration not implemented for this provider."
        )

    def deserialize_backup_entries(
        self, payload: dict[str, Any]
    ) -> ProviderBackupEntries:
        """Convert a raw backup payload into entries ready for restore."""
        raise NotImplementedError("Backup parsing not implemented for this provider.")

    async def search(self, query: str) -> Sequence[ListEntry]:
        """Search the provider for entries matching the query.

        Args:
            query (str): The search query string.

        Returns:
            Sequence[ListEntry]: A sequence of matching list entries.
        """
        ...

    async def update_entry(self, key: str, entry: ListEntry) -> ListEntry | None:
        """Update a list entry with new information.

        Args:
            key (str): The unique key of the media item to update.
            entry (ListEntry): The updated entry information.

        Returns:
            ListEntry | None: The updated list entry, or None if the update failed.
        """
        ...

    async def update_entries_batch(
        self, entries: Sequence[ListEntry]
    ) -> Sequence[ListEntry | None]:
        """Update multiple list entries in a single operation.

        This is optional and may not be supported by all providers.

        Args:
            entries (Sequence[ListEntry]): The list entries to update.

        Returns:
            Sequence[ListEntry | None]: A sequence of updated list entries, with None
                for any that could not be updated.
        """
        updated_entries: list[ListEntry | None] = []
        for entry in entries:
            updated_entry = await self.update_entry(entry.media().key, entry)
            updated_entries.append(updated_entry)
        return updated_entries

    def user(self) -> ListUser | None:
        """Get the user associated with the list.

        Returns:
            ListUser | None: The user information, or None if not available.
        """
        ...

    async def clear_cache(self) -> None:
        """Clear any cached data within the provider."""
        ...

    async def close(self) -> None:
        """Close the list provider and release any resources."""
        ...
