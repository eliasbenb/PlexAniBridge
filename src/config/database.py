from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from src import __file__ as src_file
from src import config


class PlexAniBridgeDB:
    """Database manager for PlexAniBridge application.

    Handles the creation, initialization, and migration of the SQLite database,
    including file system operations and schema management. Uses SQLModel for ORM
    and Alembic for database migrations.
    """

    def __init__(self, data_path: Path) -> None:
        """Initializes the database manager.

        Args:
            data_path (Path): Directory where the database should be stored

        Raises:
            PermissionError: If the process lacks write permissions for data_path
            ValueError: If data_path exists but is a file instead of a directory
        """
        self.data_path = data_path
        self.db_path = data_path / "plexanibridge.db"

        self.engine = self._setup_db()
        self.session = Session(self.engine)
        self._do_migrations()

    def _setup_db(self) -> Engine:
        """Creates and initializes the SQLite database.

        Performs the following setup steps:
        1. Validates or creates the data directory
        2. Imports database models to register them with SQLModel
        3. Creates a SQLAlchemy engine for database connections

        Returns:
            Engine: Configured SQLAlchemy engine instance

        Raises:
            PermissionError: If unable to create the data directory
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

        return engine

    def _do_migrations(self) -> None:
        """Executes database migrations using Alembic."""
        from alembic import command
        from alembic.config import Config

        config = Config()
        config.set_main_option(
            "script_location",
            str(Path(src_file).resolve().parent.parent / "alembic"),
        )
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

        command.upgrade(config, "head")

    def __enter__(self) -> "PlexAniBridgeDB":
        """Enters the context manager, returning the database instance."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exits the context manager, closing the session."""
        self.session.close()


db = PlexAniBridgeDB(config.DATA_PATH)
