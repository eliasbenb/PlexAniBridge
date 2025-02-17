import re
from typing import Self

from pydantic import BaseModel, Field


class TVDBMapping(BaseModel):
    """Model for parsing and validating TVDB episode mapping patterns.

    Handles conversion between string patterns and episode mapping objects.
    """

    season: int = Field(ge=-1)
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
                ^                           # Start of string
                (?P<scope>[+-])?            # Optional +/- for scope
                s(?P<season>\d+):           # Season number (required)
                (?:                         # Non-capturing group for episode part
                    (?:e(?P<start>\d+))?    # Optional start episode
                    (?:                     # Non-capturing group for end part
                        -(?:e(?P<end>\d+))?     # Optional end episode with optional number
                    )?                          # End part is optional
                    |                       # OR
                    -e(?P<before>\d+)           # Single episode with leading dash
                )?                          # Entire episode part is optional
                (?:\|(?P<ratio>-?\d+))?     # Optional ratio with pipe
                $                           # End of string
            """,
            re.VERBOSE,
        )

        match = PATTERN.match(s)
        if not match:
            return None

        groups = match.groupdict()

        season = int(groups["season"])

        if groups["before"]:
            end = int(groups["before"])
            start = 1
        else:
            start = int(groups["start"]) if groups["start"] else 1
            end = int(groups["end"]) if groups["end"] else None

        ratio = int(groups["ratio"]) if groups["ratio"] else 1

        kwargs = {
            "season": season,
            "start": start,
            "end": end,
            "ratio": ratio,
        }
        return cls(**{k: v for k, v in kwargs.items() if v is not None})

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
