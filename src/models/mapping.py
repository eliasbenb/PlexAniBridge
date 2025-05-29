import re

from pydantic import BaseModel, Field


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
    def from_string(cls, season: int, s: str) -> list["TVDBMapping"]:
        """Parse a string pattern into a TVDBMapping instance.
        Args:
            season (int): Season number
            s (str): Pattern string in format 'e{start}-e{end}|{ratio},e{start2}-e{end2}|{ratio2}'
                    Examples:
                    - 'e1-e12|2'
                    - 'e12-,e2'
                    - 'e1-e5,e8-e10'
                    - '' (empty string for full season)
        Returns:
            TVDBMapping | None: New TVDBMapping instance if pattern is valid, None otherwise
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

    class Config:
        slots = True
