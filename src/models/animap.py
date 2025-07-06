from functools import cached_property

from sqlalchemy import JSON, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.models.mapping import TVDBMapping


class AniMap(Base):
    """Model for the animap table."""

    __tablename__ = "animap"

    anilist_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anidb_id: Mapped[int | None] = mapped_column(Integer, index=False, nullable=True)
    imdb_id: Mapped[list[str] | None] = mapped_column(JSON, index=True, nullable=True)
    mal_id: Mapped[list[int] | None] = mapped_column(JSON, index=False, nullable=True)
    tmdb_movie_id: Mapped[list[int] | None] = mapped_column(
        JSON, index=True, nullable=True
    )
    tmdb_show_id: Mapped[list[int] | None] = mapped_column(
        JSON, index=True, nullable=True
    )
    tvdb_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    tvdb_mappings: Mapped[dict[str, str] | None] = mapped_column(
        JSON, index=True, nullable=True
    )

    __table_args__ = (
        Index("idx_imdb_tmdb", "imdb_id", "tmdb_movie_id"),
        Index("idx_tvdb_season", "tvdb_id", "tvdb_mappings"),
    )

    def __init__(self, **kwargs) -> None:
        """Initialize AniMap with data validation."""
        # Convert single values to lists for specific fields
        for field in ("imdb_id", "mal_id", "tmdb_movie_id", "tmdb_show_id"):
            if field in kwargs:
                kwargs[field] = self._convert_to_list(kwargs[field])

        super().__init__(**kwargs)

    @staticmethod
    def _convert_to_list(v) -> list | None:
        """Convert single values to lists.

        Args:
            v: Value to convert

        Returns:
            list | None: List of values
        """
        if v is None:
            return v
        if not isinstance(v, list):
            return [v]
        return v

    @cached_property
    def length(self) -> int:
        return sum(m.length for m in self.parsed_tvdb_mappings)

    @cached_property
    def parsed_tvdb_mappings(self) -> list[TVDBMapping]:
        res: list[TVDBMapping] = []

        if not self.tvdb_mappings:
            return res

        for season, s in self.tvdb_mappings.items():
            try:
                parsed = TVDBMapping.from_string(int(season.lstrip("s")), s)
                res.extend(parsed)
            except ValueError:
                continue
        return res

    def __hash__(self) -> int:
        return hash(self.__repr__())

    def __repr__(self):
        return f"<{':'.join(f'{k}={v}' for k, v in self.__dict__.items() if v is not None and not k.startswith('_'))}>"
