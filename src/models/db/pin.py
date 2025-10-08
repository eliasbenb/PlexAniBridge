"""Pin model for per-profile AniList field pinning."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.db.base import Base


class Pin(Base):
    """Model representing pinned AniList fields for a profile entry."""

    __tablename__ = "pin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_name: Mapped[str] = mapped_column(String, index=True)
    anilist_id: Mapped[int] = mapped_column(Integer, index=True)
    fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_pin_profile_anilist", "profile_name", "anilist_id", unique=True),
    )
