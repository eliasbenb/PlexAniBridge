from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from src.settings import config


class PlexAniBridgeDB:
    """A class to manage the creation and initialization of the database"""

    def __init__(self, db_path: str) -> None:
        self.db_path: Path = Path(db_path)

        self.engine = self.__setup_db()

    def __setup_db(self) -> Engine:
        """Creates and initializes the database

        Returns:
            Engine: The database engine
        """
        if not self.db_path.exists():
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise PermissionError(f"Cannot create {self.db_path.parent}.")
        elif not self.db_path.is_file():
            raise ValueError(f"Path {self.db_path} is not a file.")

        engine = create_engine(f"sqlite:///{self.db_path}")
        SQLModel.metadata.create_all(engine)
        return engine


db = PlexAniBridgeDB(config.DB_PATH).engine
