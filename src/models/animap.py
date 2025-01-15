from sqlmodel import JSON, Field, SQLModel


class AniMap(SQLModel, table=True):
    """Model for the animap table."""

    __tablename__ = "animap"

    anilist_id: int = Field(primary_key=True)
    anidb_id: int | None = Field(index=True)
    imdb_id: list[str] | None = Field(sa_type=JSON(none_as_null=True), index=True)
    mal_id: list[int] | None = Field(sa_type=JSON(none_as_null=True), index=True)
    tmdb_movie_id: list[int] | None = Field(sa_type=JSON(none_as_null=True), index=True)
    tmdb_show_id: list[int] | None = Field(sa_type=JSON(none_as_null=True), index=True)
    tvdb_id: int | None = Field(index=True)
    tvdb_epoffset: int | None
    tvdb_season: int | None
