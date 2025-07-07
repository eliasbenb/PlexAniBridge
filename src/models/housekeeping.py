from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Housekeeping(Base):
    """Model for the Housekeeping table.

    This table is used to store miscellaneous data such as timestamps and hashes.
    """

    __tablename__ = "house_keeping"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(String, nullable=True)
