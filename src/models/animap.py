from sqlmodel import Field, SQLModel, JSON
from typing import Optional


class AniMap(SQLModel, table=True):
    __tablename__ = "animap"

    anidb_id: int = Field(primary_key=True)
    anilist_id: Optional[list[int]] = Field(sa_type=JSON(int), index=True)
    imdb_id: Optional[list[str]] = Field(sa_type=JSON(str), index=True)
    mal_id: Optional[list[int]] = Field(sa_type=JSON(int), index=True)
    tmdb_movie_id: Optional[int] = Field(index=True)
    tmdb_show_id: Optional[int] = Field(index=True)
    tvdb_epoffset: Optional[int]
    tvdb_id: Optional[int] = Field(index=True)
    tvdb_season: Optional[int]


class AniMapHouseKeeping(SQLModel, table=True):
    __tablename__ = "animap_house_keeping"

    key: str = Field(primary_key=True)
    value: Optional[str]
