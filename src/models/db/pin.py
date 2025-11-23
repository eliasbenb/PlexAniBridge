"""Pin model for per-profile AniList field pinning."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.db.base import Base

__all__ = ["Pin"]


class Pin(Base):
    """Model representing pinned AniList fields for a profile entry."""

    __tablename__ = "pin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_name: Mapped[str] = mapped_column(String, index=True)

    list_namespace: Mapped[str] = mapped_column(String, index=True)
    list_media_key: Mapped[str] = mapped_column(String, index=True)

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
        Index(
            "ix_pin_profile_list_keys",
            "profile_name",
            "list_namespace",
            "list_media_key",
            unique=True,
        ),
    )
