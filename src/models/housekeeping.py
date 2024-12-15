from sqlmodel import Field, SQLModel
from typing import Optional


class Housekeeping(SQLModel, table=True):
    __tablename__ = "house_keeping"

    key: str = Field(primary_key=True)
    value: Optional[str]
