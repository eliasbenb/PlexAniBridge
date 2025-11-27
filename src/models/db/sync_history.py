"""Sync History Database Model."""

from datetime import UTC, datetime
from typing import Any

from anibridge.library import MediaKind
from sqlalchemy import JSON, DateTime, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.sync.stats import SyncOutcome
from src.models.db.base import Base

__all__ = ["SyncHistory", "SyncOutcome"]


class SyncHistory(Base):
    """Model for tracking individual item sync operations."""

    __tablename__ = "sync_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_name: Mapped[str] = mapped_column(String, index=True)

    library_namespace: Mapped[str] = mapped_column(String, index=True)
    library_section_key: Mapped[str] = mapped_column(String, index=True)
    library_media_key: Mapped[str] = mapped_column(String, index=True)

    list_namespace: Mapped[str] = mapped_column(String, index=True)
    list_media_key: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )

    media_kind: Mapped[MediaKind] = mapped_column(Enum(MediaKind), index=True)
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
            "library_namespace",
            "library_section_key",
            "library_media_key",
            "list_namespace",
            "list_media_key",
            "outcome",
        ),
    )
