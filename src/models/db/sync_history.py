"""Sync History Database Model."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.providers.library import MediaKind
from src.models.db.base import Base

__all__ = ["SyncHistory", "SyncOutcome"]


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
    plex_type: Mapped[MediaKind] = mapped_column(Enum(MediaKind), index=True)
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
