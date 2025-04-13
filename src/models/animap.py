from functools import cached_property
from typing import Any

from pydantic import field_validator
from sqlmodel import JSON, Field, SQLModel

from .mapping import TVDBMapping


def TypedJson(*args, **kwargs) -> Any:
    return JSON(*args, **kwargs)


class AniMap(SQLModel, table=True):
    """Model for the animap table."""

    __tablename__: str = "animap"  #  type: ignore

    anilist_id: int = Field(primary_key=True)
    anidb_id: int | None = Field(index=False)
    imdb_id: list[str] | None = Field(sa_type=TypedJson(none_as_null=True), index=True)
    mal_id: list[int] | None = Field(sa_type=TypedJson(none_as_null=True), index=False)
    tmdb_movie_id: list[int] | None = Field(
        sa_type=TypedJson(none_as_null=True), index=True
    )
    tmdb_show_id: list[int] | None = Field(
        sa_type=TypedJson(none_as_null=True), index=True
    )
    tvdb_id: int | None = Field(index=True)
    tvdb_mappings: dict[str, str] | None = Field(
        sa_type=TypedJson(none_as_null=True),
        index=False,
    )

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

    @field_validator(
        "imdb_id", "mal_id", "tmdb_movie_id", "tmdb_show_id", mode="before"
    )
    def convert_to_list(cls, v) -> list | None:
        """Convert single values to lists.

        Args:
            cls: Class instance
            v: Value to convert

        Returns:
            list | None: List of values
        """
        if v is None:
            return v
        if not isinstance(v, list):
            return [v]
        return v

    def __hash__(self) -> int:
        return hash(self.__repr__())

    def __repr__(self):
        return f"<{':'.join(f'{k}={v}' for k, v in self.model_dump().items() if v is not None)}>"
