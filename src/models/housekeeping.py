from typing import Optional

from sqlmodel import Field, SQLModel


class Housekeeping(SQLModel, table=True):
    __tablename__ = "house_keeping"

    key: str = Field(primary_key=True)
    value: Optional[str]
