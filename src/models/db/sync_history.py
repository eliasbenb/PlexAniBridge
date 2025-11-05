"""Sync History Database Model."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from plexapi.video import Episode, Movie, Season, Show
from sqlalchemy import JSON, DateTime, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.exceptions import UnsupportedMediaTypeError
from src.models.db.base import Base

__all__ = ["MediaType", "SyncHistory", "SyncOutcome"]


class MediaType(StrEnum):
    """Enumeration of media types for Plex items."""

    MOVIE = "movie"
    SHOW = "show"
    SEASON = "season"
    EPISODE = "episode"

    @classmethod
    def from_item(cls, item: Movie | Show | Season | Episode) -> MediaType:
        """Get the media type from a Plex item.

        Args:
            item (Movie | Show | Season | Episode): Plex media item

        Returns:
            MediaType: Corresponding media type enum value.
        """
        if isinstance(item, Movie):
            return cls.MOVIE
        elif isinstance(item, Show):
            return cls.SHOW
        elif isinstance(item, Season):
            return cls.SEASON
        elif isinstance(item, Episode):
            return cls.EPISODE
        else:
            raise UnsupportedMediaTypeError(f"Unsupported media type: {type(item)}")

    def to_cls(self) -> type[Movie | Show | Season | Episode]:
        """Get the corresponding Plex class for this media type.

        Returns:
            type[Movie | Show | Season | Episode]: The Plex class for this media type.
        """
        match self:
            case self.MOVIE:
                return Movie
            case self.SHOW:
                return Show
            case self.SEASON:
                return Season
            case self.EPISODE:
                return Episode
            case _:
                raise UnsupportedMediaTypeError(f"Unsupported media type: {self}")


class SyncOutcome(StrEnum):
    """Enumeration of possible synchronization outcomes for media items."""

    SYNCED = "synced"  # Successfully synchronized to AniList
    SKIPPED = "skipped"  # Item already up to date, no changes needed
    FAILED = "failed"  # Failed to process due to error
    NOT_FOUND = "not_found"  # No matching AniList entry could be found
    DELETED = "deleted"  # Item was deleted from AniList (destructive sync)
    PENDING = "pending"  # Item was identified for processing but not yet processed
    UNDONE = "undone"  # Resulting entry produced by an explicit user undo action


class SyncHistory(Base):
    """Model for tracking individual item sync operations."""

    __tablename__ = "sync_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_name: Mapped[str] = mapped_column(String, index=True)
    plex_guid: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    plex_rating_key: Mapped[str] = mapped_column(String)
    plex_child_rating_key: Mapped[str | None] = mapped_column(String)
    plex_type: Mapped[MediaType] = mapped_column(Enum(MediaType), index=True)
    anilist_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[SyncOutcome] = mapped_column(Enum(SyncOutcome), index=True)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=dict, nullable=True
    )
    after_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=dict, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(
        String, default=None, nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (
        Index(
            "ix_sync_history_upsert_keys",
            "profile_name",
            "plex_rating_key",
            "plex_child_rating_key",
            "plex_type",
            "outcome",
        ),
    )
