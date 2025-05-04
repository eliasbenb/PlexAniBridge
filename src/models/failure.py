from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Failure(SQLModel, table=True):
    """Model for the failure table which stores information about failed syncs.

    This table is only used for polling scans to record and retry failed syncs.
    """

    __tablename__: str = "failure"  # type: ignore

    anilist_account_id: int = Field(primary_key=True)
    plex_account_id: int = Field(primary_key=True)
    section_id: int = Field(primary_key=True)
    rating_key: str = Field(primary_key=True)
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
