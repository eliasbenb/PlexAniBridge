"""AniMap Model."""

from __future__ import annotations

import re
from functools import cached_property

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.models.db.base import Base


class TVDBMapping(BaseModel):
    """Model for parsing and validating TVDB episode mapping patterns.

    Handles conversion between string patterns and episode mapping objects.
    """

    season: int = Field(ge=0)
    start: int = Field(default=1, gt=0)
    end: int | None = Field(default=None, gt=0)
    ratio: int = Field(default=1)

    @property
    def length(self) -> int:
        """Calculate the number of episodes in the range.

        Returns:
            int: Number of episodes in the range or -1 if the end is not specified
        """
        return self.end - self.start + 1 if self.end else -1

    @classmethod
    def from_string(cls, season: int, s: str) -> list[TVDBMapping]:
        """Parse a string pattern into a TVDBMapping instance.

        Args:
            season (int): Season number
            s (str): Pattern string in format
                    'e{start}-e{end}|{ratio},e{start2}-e{end2}|{ratio2}'
                    Examples:
                    - 'e1-e12|2'
                    - 'e12-,e2'
                    - 'e1-e5,e8-e10'
                    - '' (empty string for full season)

        Returns:
            TVDBMapping | None: New TVDBMapping instance if pattern is valid, None
                                otherwise
        """
        PATTERN = re.compile(
            r"""
            (?:^|,)
            (?:
                (?P<is_ep_range>                # Episode range (e.g. e1-e4)
                    e(?P<range_start>\d+)
                    -
                    e(?P<range_end>\d+)
                )
                |
                (?P<is_open_ep_range_after>     # Open range after (e.g. e1-)
                    e(?P<after_start>\d+)-(?=\||$|,)
                )
                |
                (?P<is_single_ep>               # Single episode (e.g. e2)
                    e(?P<single_ep>\d+)(?!-)
                )
                |
                (?P<is_open_ep_range_before>    # Open range before (e.g. -e5)
                    -e(?P<before_end>\d+)
                )
            )
            (?:\|(?P<ratio>-?\d+))?            # Optional ratio for each range
            """,
            re.VERBOSE,
        )

        if not s:
            return [cls(season=season)]

        range_matches = list(PATTERN.finditer(s))

        episode_ranges = []
        for match in range_matches:
            groups = match.groupdict()
            ratio = int(groups["ratio"]) if groups["ratio"] else 1

            # Explicit start and end episode range
            if groups["is_ep_range"]:
                start = int(groups["range_start"])
                end = int(groups["range_end"])
            # Single episode
            elif groups["is_single_ep"]:
                start = end = int(groups["single_ep"])
            # Open range with unknown start and explicit end
            elif groups["is_open_ep_range_before"]:
                start = 1
                end = int(groups["before_end"])
            # Open range with explicit start and unknown end
            elif groups["is_open_ep_range_after"]:
                start = int(groups["after_start"])
                end = None
            else:
                continue

            episode_ranges.append(cls(season=season, start=start, end=end, ratio=ratio))

        return episode_ranges

    def __str__(self) -> str:
        """Generate a string representation of the TVDBMapping instance.

        Returns:
            str: String representation in format 'S{season}E{start}-{end}|{ratio}'
        """
        season = f"S{self.season:02d}"
        if self.start == 1 and self.end is None:
            return season
        result = f"{season}E{self.start:02d}"
        return result + (
            "+"
            if self.end is None and self.start != 1
            else f"-E{self.end:02d}"
            if self.end and self.end != self.start
            else ""
        )

    def __hash__(self) -> int:
        """Generate a hash for the TVDBMapping instance.

        Returns:
            int: Hash value of the instance
        """
        return hash(repr(self))


class AniMap(Base):
    """Model for the animap table."""

    __tablename__ = "animap"

    anilist_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anidb_id: Mapped[int | None] = mapped_column(
        Integer, index=False, nullable=True, default=None
    )
    imdb_id: Mapped[list[str] | None] = mapped_column(
        JSON, index=True, nullable=True, default=None
    )
    mal_id: Mapped[list[int] | None] = mapped_column(
        JSON, index=False, nullable=True, default=None
    )
    tmdb_movie_id: Mapped[list[int] | None] = mapped_column(
        JSON, index=True, nullable=True, default=None
    )
    tmdb_show_id: Mapped[list[int] | None] = mapped_column(
        JSON, index=True, nullable=True, default=None
    )
    tvdb_id: Mapped[int | None] = mapped_column(
        Integer, index=True, nullable=True, default=None
    )

    tmdb_mappings: Mapped[dict[str, str] | None] = mapped_column(
        JSON, index=True, nullable=True, default=None
    )
    tvdb_mappings: Mapped[dict[str, str] | None] = mapped_column(
        JSON, index=True, nullable=True, default=None
    )

    __table_args__ = (
        Index("idx_imdb_tmdb", "imdb_id", "tmdb_movie_id"),
        Index("idx_tmdb_season", "tmdb_show_id", "tmdb_mappings"),
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
        """Calculate the total length of all TVDB mappings.

        Returns:
            int: Total length of all TVDB mappings
        """
        return sum(m.length for m in self.parsed_tvdb_mappings)

    @cached_property
    def parsed_tvdb_mappings(self) -> list[TVDBMapping]:
        """Parse TVDB mappings into a list of TVDBMapping objects.

        Returns:
            list[TVDBMapping]: List of parsed TVDBMapping objects
        """
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
        """Generate a hash for the AniMap instance.

        Returns:
            int: Hash value of the instance
        """
        return hash(self.__repr__())

    def __repr__(self):
        """Generate a string representation of the AniMap instance.

        Returns:
            str: String representation of the instance
        """
        return f"<{
            ':'.join(
                f'{k}={v}'
                for k, v in self.__dict__.items()
                if v is not None and not k.startswith('_')
            )
        }>"
