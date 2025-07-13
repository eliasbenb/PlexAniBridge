from pathlib import Path
from types import TracebackType

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src import __file__ as src_file
from src import config

__all__ = ["PlexAniBridgeDB", "db"]


class PlexAniBridgeDB:
    """Database manager for PlexAniBridge application.

    Handles the creation, initialization, and migration of the SQLite database,
    including file system operations and schema management. Uses SQLAlchemy for ORM
    and Alembic for database migrations.

    During initialization, this class automatically imports all database models
    and runs any pending migrations.

    Can be used as a context manager to automatically close the database session.
    """

    def __init__(self, data_path: Path) -> None:
        """Initializes the database manager.

        Performs database setup including directory creation, model registration,
        engine creation, session initialization, and migration execution.

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
        2. Imports database models to register them with SQLAlchemy
        3. Creates a SQLAlchemy engine for database connections

        Returns:
            Engine: Configured SQLAlchemy engine instance

        Raises:
            PermissionError: If unable to create the data directory
            ValueError: If data_path exists but is a file instead of a directory
        """
        import src.models  # noqa: F401

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
        """Executes database migrations using Alembic.

        Configures Alembic to use the SQLite database and runs all pending
        migrations to bring the schema up to the latest version.

        Raises:
            AlembicError: If migration execution fails
            FileNotFoundError: If Alembic migration scripts are not found
        """
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
        """Enters the context manager, returning the database instance.

        Returns:
            PlexAniBridgeDB: This database instance
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exits the context manager, closing the session.

        Args:
            exc_type (type[BaseException] | None): Exception type if an exception occurred
            exc_val (BaseException | None): Exception value if an exception occurred
            exc_tb (TracebackType | None): Exception traceback if an exception occurred
        """
        self.session.close()


db = PlexAniBridgeDB(config.data_path)
