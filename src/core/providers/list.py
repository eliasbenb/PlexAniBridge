"""List provider protocols for media libraries."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Protocol, runtime_checkable


class ListStatus(StrEnum):
    """Supported statuses for media items in a list."""

    COMPLETED = "completed"
    CURRENT = "current"
    DROPPED = "dropped"
    PAUSED = "paused"
    PLANNING = "planning"
    REPEATING = "repeating"


@dataclass(frozen=True, slots=True)
class ListUser:
    """User information for a media list."""

    key: str  # Any unique identifier for the user
    display_name: str


@runtime_checkable
class ListEntity(Protocol):
    """Base protocol for list entities."""

    key: str
    title: str

    # Any additional metadata that may be used downstream
    extras: dict | None = None

    def provider(self) -> ListProvider:
        """Get the list provider this entity belongs to.

        Returns:
            ListProvider: The list provider.
        """
        ...

    def __hash__(self) -> int:
        """Compute the hash based on the entity's key."""
        return hash(self.provider().NAMESPACE + self.key)

    def __repr__(self) -> str:
        """Return a string representation of the list entity."""
        return (
            f"<{self.__class__.__name__}:{self.provider().NAMESPACE}:{self.key}:"
            f"{self.title[:32]}>"
        )


@runtime_checkable
class ListEntry(ListEntity, Protocol):
    """Base protocol for list entries."""

    @property
    def progress(self) -> int:
        """Get the progress for the entry.

        Returns:
            int: The progress integer (e.g., episodes watched).
        """
        ...

    @property
    def repeats(self) -> int:
        """Get the repeat count for the entry.

        If not available by the list provider, return 0.

        Returns:
            int: The number of times repeated.
        """
        ...

    @property
    def review(self) -> str | None:
        """Get the user's review for the entry.

        Returns:
            str | None: The user's review text, or None if not reviewed.
        """
        ...

    @property
    def status(self) -> ListStatus | None:
        """Get the status of the entry in the list.

        Returns:
            ListStatus | None: The watch status.
        """
        ...

    @property
    def user_rating(self) -> int | None:
        """Get the user rating for the list entry.

        Returns:
            int | None: The user rating on a 0-100 scale, or None if not rated.
        """
        ...

    @property
    def started_at(self) -> datetime | None:
        """Get the timestamp when the user started watching the entry.

        Returns:
            datetime | None: The UTC timestamp when started, or None if not started.
        """
        ...

    @property
    def finished_at(self) -> datetime | None:
        """Get the timestamp when the user finished watching the entry.

        This is the timestamp when the entry was completed for the *first* time.

        Returns:
            datetime | None: The UTC timestamp when finished, or None if not finished.
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

    async def backup_list(self) -> str:
        """Backup the entire list from the provider.

        It is up to the implementation to decide the format of the backup data. Whatever
        format, it should be serializable/deserializable in string form.

        Returns:
            str: A serialized string representation of all list entries.
        """
        ...

    async def delete_entry(self, media_key: str) -> None:
        """Delete a list entry by its media key.

        Args:
            media_key (str): The unique key of the media item to delete.
        """
        ...

    async def get_entry(self, media_key: str) -> ListEntry | None:
        """Retrieve a list entry by its media key.

        Args:
            media_key (str): The unique key of the media item to retrieve.

        Returns:
            ListEntry | None: The list entry if found, otherwise None.
        """
        ...

    async def restore_list(self, backup: str) -> None:
        """Restore the list from a backup sequence of list entries.

        Args:
            backup (str): The serialized string representation of the list entries.
        """
        ...

    async def search(self, query: str) -> Sequence[ListEntry]:
        """Search the provider for entries matching the query.

        Args:
            query (str): The search query string.

        Returns:
            Sequence[ListEntry]: A sequence of matching list entries.
        """
        ...

    async def update_entry(self, media_key: str, entry: ListEntry) -> None:
        """Update a list entry with new information.

        Args:
            media_key (str): The unique key of the media item to update.
            entry (ListEntry): The updated entry information.
        """
        ...

    async def user(self) -> ListUser | None:
        """Get the user associated with the list.

        Returns:
            ListUser | None: The user information, or None if not available.
        """
        ...

    def clear_cache(self) -> None:
        """Clear any cached data within the provider."""
        ...

    async def close(self) -> None:
        """Close the list provider and release any resources."""
        ...
