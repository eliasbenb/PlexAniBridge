"""AniMap Provenance Model."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.db.base import Base

__all__ = ["AniMapProvenance"]


class AniMapProvenance(Base):
    """Tracks the provenance (source paths/URLs) for each AniMap row.

    Stores one row per source with an order column ``n`` to preserve the
    original order of sources for a given ``anilist_id``.
    """

    __tablename__ = "animap_provenance"

    anilist_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("animap.anilist_id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    n: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
