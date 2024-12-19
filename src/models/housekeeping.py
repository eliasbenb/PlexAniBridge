from typing import Optional

from sqlmodel import Field, SQLModel


class Housekeeping(SQLModel, table=True):
    """Model for the Housekeeping table

    This table is used to store miscellaneous data such as timestamps and hashes.
    """

    __tablename__ = "house_keeping"

    key: str = Field(primary_key=True)
    value: Optional[str]
