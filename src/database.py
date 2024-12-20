from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine


class PlexAniBridgeDB:
    """A class to manage the creation and initialization of the database"""

    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self.db_path = data_path / "plexanibridge.db"

        self.engine = self.__setup_db()

    def __setup_db(self) -> Engine:
        """Creates and initializes the database

        Returns:
            Engine: The database engine
        """
        import src.models.animap  # noqa: F401
        import src.models.housekeeping  # noqa: F401

        if not self.data_path.exists():
            try:
                self.data_path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise PermissionError(
                    f"{self.__class__.__name__}: You do not have permissions to create "
                    f"files at '{self.data_path}'"
                )
        elif self.data_path.is_file():
            raise ValueError(
                f"{self.__class__.__name__}: The path '{self.data_path}' is a file, "
                f"please delete it first or choose a different data folder path"
            )

        engine = create_engine(f"sqlite:///{self.db_path}")
        SQLModel.metadata.create_all(engine)
        return engine
