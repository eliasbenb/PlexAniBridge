import re
from typing import Self

from pydantic import BaseModel, Field


class TVDBMapping(BaseModel):
    """Model for parsing and validating TVDB episode mapping patterns.

    Handles conversion between string patterns and episode mapping objects.
    """

    season: int = Field(ge=0)
    start: int = Field(default=1, ge=0)
    end: int | None = Field(default=None, ge=0)
    ratio: int = Field(default=1)

    @classmethod
    def from_string(cls, s: str) -> Self | None:
        """Parse a string pattern into a TVDBMapping instance.

        Args:
            s (str): Pattern string in format 's{season}:e{start}-e{end}|{ratio}'
                    Example: 's1:e1-e12|2' or 's1:'

        Returns:
            Self | None: New TVDBMapping instance if pattern is valid, None otherwise
        """
        PATTERN = re.compile(
            r"""
            ^
            s(?P<season>\d+):                   # Season number (required)
            (?:
                (?P<is_ep_range>                # Episode range (e.g. s1:e1-e4)
                    e(?P<range_start>\d+)
                    -
                    e(?P<range_end>\d+)
                )
                |
                (?P<is_single_ep>               # Single episode (e.g. s1:e2)
                    e(?P<single_ep>\d+)
                    (?!-)
                )
                |
                (?P<is_open_ep_range_before>    # Open range before (e.g. s1:-e5)
                    -e(?P<before_end>\d+)
                )
                |
                (?P<is_open_ep_range_after>     # Open range after (e.g. s1:e1-)
                    e(?P<after_start>\d+)-
                )
            )?
            (?:\|(?P<ratio>-?\d+))?             # Optional ratio for each episode
            $
            """,
            re.VERBOSE,
        )

        match = PATTERN.match(s)
        if not match:
            return None

        groups = match.groupdict()

        season = int(groups["season"])
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
        # Open range starting from episode 1 (full season)
        else:
            start = 1
            end = None

        return cls(
            season=season,
            start=start,
            end=end,
            ratio=ratio,
        )

    def __contains__(self, episode: tuple[int, int]) -> bool:
        """Check if a season/episode tuple falls within this mapping's range.

        Args:
            episode (tuple[int, int]): Tuple of (season_number, episode_number)

        Returns:
            bool: True if episode is within mapping range, False otherwise
        """
        if self.season != episode[0]:
            return False
        if self.end is not None:
            return self.start <= episode[1] <= self.end
        return self.start <= episode[1]

    def __repr__(self) -> str:
        """Convert the mapping object to its string representation.

        Returns:
            str: String in format 's{season}:e{start}|{ratio}'
        """
        return f"s{self.season}:e{self.start}" + (
            f"|{self.ratio}" if self.ratio is not None else ""
        )

    def __str__(self) -> str:
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
        return hash(repr(self))
