from sqlmodel import Field, SQLModel


class Housekeeping(SQLModel, table=True):
    """Model for the Housekeeping table.

    This table is used to store miscellaneous data such as timestamps and hashes.
    """

    __tablename__: str = "house_keeping"  # type: ignore

    key: str = Field(primary_key=True)
    value: str | None
