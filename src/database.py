from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import create_engine

from src import config


class PlexAniBridgeDB:
    """Database manager for PlexAniBridge application.

    Handles the creation, initialization, and migration of the SQLite database,
    including file system operations and schema management. Uses SQLModel for ORM
    and Alembic for database migrations.

    The database structure consists of:
    - animap: Stores anime ID mappings between different services
    - housekeeping: Stores application metadata and state

    Attributes:
        data_path (Path): Directory where database and related files are stored
        db_path (Path): Full path to the SQLite database file
        engine (Engine): SQLAlchemy engine instance for database connections

    File Structure:
        {data_path}/
        └── plexanibridge.db    # SQLite database file
    """

    def __init__(self, data_path: Path) -> None:
        """Initializes the database manager.

        Args:
            data_path (Path): Directory where the database should be stored

        Raises:
            PermissionError: If the process lacks write permissions for data_path
            ValueError: If data_path exists but is a file instead of a directory

        Note:
            Creates the data directory if it doesn't exist
            Automatically runs database migrations after initialization
        """
        self.data_path = data_path
        self.db_path = data_path / "plexanibridge.db"

        self.engine = self._setup_db()
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
            ValueError: If data_path is a file instead of a directory

        Note:
            - Uses SQLite as the database backend
            - Models are imported here to ensure they're registered
            - Does not create tables (handled by migrations)
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
        """Executes database migrations using Alembic.

        Uses Alembic to manage database schema changes by:
        1. Locating and loading the Alembic configuration
        2. Setting up the migration environment
        3. Upgrading the database to the latest schema version

        Migration Details:
            - Migrations are stored in the 'alembic' directory
            - Automatically detects and applies pending migrations
            - Uses 'head' revision (latest schema version)
            - Maintains migration history in the database

        Note:
            This method should be called after database initialization
            but before any database operations are performed
        """
        from alembic import command
        from alembic.config import Config

        config = Config()
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parent.parent / "alembic")
        )
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

        command.upgrade(config, "head")


db = PlexAniBridgeDB(config.DATA_PATH)
