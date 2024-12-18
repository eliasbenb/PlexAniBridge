from typing import Optional

from sqlmodel import JSON, Field, SQLModel


class AniMap(SQLModel, table=True):
    """Model for the animap table"""

    __tablename__ = "animap"

    anidb_id: int = Field(primary_key=True)
    anilist_id: Optional[list[int]] = Field(sa_type=JSON, index=True)
    imdb_id: Optional[list[str]] = Field(sa_type=JSON, index=True)
    mal_id: Optional[list[int]] = Field(sa_type=JSON, index=True)
    tmdb_movie_id: Optional[int] = Field(index=True)
    tmdb_show_id: Optional[int] = Field(index=True)
    tvdb_epoffset: Optional[int]
    tvdb_id: Optional[int] = Field(index=True)
    tvdb_season: Optional[int]
