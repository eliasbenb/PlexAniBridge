from enum import StrEnum
from hashlib import md5
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class SyncField(StrEnum):
    """Enumeration of AniList fields that can be synchronized with Plex.

    These fields represent the data that can be synchronized between Plex
    and AniList for each media entry. Each enum value corresponds to an
    AniList API field name in snake_case format.

    Values:
        STATUS: Watch status (watching, completed, etc.)
        SCORE: User rating
        PROGRESS: Number of episodes/movies watched
        REPEAT: Number of times rewatched
        NOTES: User's notes/comments
        STARTED_AT: When the user started watching
        COMPLETED_AT: When the user finished watching

    Note:
        Values are stored in snake_case but can be converted to camelCase
        for AniList API compatibility using to_camel()
    """

    STATUS = "status"
    SCORE = "score"
    PROGRESS = "progress"
    REPEAT = "repeat"
    NOTES = "notes"
    STARTED_AT = "started_at"
    COMPLETED_AT = "completed_at"

    def to_camel(self) -> str:
        """Converts the field name to camelCase for AniList API compatibility.

        Returns:
            str: The field name in camelCase format
                Example: 'started_at' -> 'startedAt'
        """
        return to_camel(self.value)

    def __repr__(self) -> str:
        """Provides a string representation of the enum value.

        Returns:
            str: Quoted string of the field name
                Example: SyncField.STATUS -> 'status'
        """
        return f"'{self.value}'"


class LogLevel(StrEnum):
    """Enumeration of available logging levels.

    Standard Python logging levels used to control log output verbosity.
    Ordered from most verbose (DEBUG) to least verbose (CRITICAL).

    Values:
        DEBUG: Detailed information for debugging
        INFO: General information about program execution
        WARNING: Indicates a potential problem
        ERROR: Error that prevented a specific operation
        CRITICAL: Error that prevents further program execution
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __repr__(self) -> str:
        """Provides a string representation of the log level.

        Returns:
            str: Quoted string of the log level
                Example: LogLevel.DEBUG -> 'DEBUG'
        """
        return f"'{self.value}'"


class PlexAnibridgeConfig(BaseSettings):
    """Configuration manager for PlexAniBridge application.

    Handles loading, validation, and storage of configuration settings from
    environment variables or .env file. Provides type checking and validation
    rules for all settings.

    Settings Categories:
        AniList Settings:
            ANILIST_TOKEN (str | list[str]): Authentication token(s) for AniList API

        Plex Settings:
            PLEX_TOKEN (str): Authentication token for Plex server
            PLEX_USER (str | list[str]): Plex username(s) to sync
            PLEX_URL (str): Plex server URL, defaults to "http://localhost:32400"
            PLEX_SECTIONS (list[str]): Library sections to sync

        General Settings:
            SYNC_INTERVAL (int): Time between syncs in seconds (>= -1)
            POLLING_SCAN (bool): Enable polling for new media, default False
            FULL_SCAN (bool): Enable a full scan of all media, even if not watched, default False
            DESTRUCTIVE_SYNC (bool): Allow deletion of entries, default False
            EXCLUDED_SYNC_FIELDS (list[SyncField]): Fields to ignore during sync

        Advanced Settings:
            DATA_PATH (Path): Storage location for database and logs
            DRY_RUN (bool): Simulate operations without making changes
            LOG_LEVEL (LogLevel): Logging verbosity
            FUZZY_SEARCH_THRESHOLD (int): Title matching threshold (0-100)

    Environment Variables:
        All settings can be configured via environment variables.
        Lists should be comma-separated.
        Example: PLEX_SECTIONS=Anime,Movies

    File Configuration:
        Settings can also be loaded from a .env file in the current directory.

    Validation Rules:
        - DATA_PATH is converted to absolute path
        - ANILIST_TOKEN and PLEX_USER must have matching lengths
        - SYNC_INTERVAL must be >= -1
        - FUZZY_SEARCH_THRESHOLD must be between 0 and 100
    """

    # AniList
    ANILIST_TOKEN: str | list[str]

    # Plex
    PLEX_TOKEN: str
    PLEX_USER: str | list[str]
    PLEX_URL: str = "http://localhost:32400"
    PLEX_SECTIONS: list[str]

    # General
    SYNC_INTERVAL: int = Field(3600, ge=-1)
    POLLING_SCAN: bool = False
    FULL_SCAN: bool = False
    DESTRUCTIVE_SYNC: bool = False

    EXCLUDED_SYNC_FIELDS: list[SyncField] = ["notes", "score"]

    # Advanced
    DATA_PATH: Path = "./data"
    DRY_RUN: bool = False
    LOG_LEVEL: LogLevel = LogLevel.INFO
    FUZZY_SEARCH_THRESHOLD: int = Field(90, ge=0, le=100)

    @model_validator(mode="after")
    def absolute_data_path(self) -> Self:
        """Ensures DATA_PATH is an absolute path.

        Converts relative paths to absolute using the current working directory
        as the base.

        Returns:
            PlexAnibridgeConfig: Self with validated DATA_PATH

        Example:
            "./data" -> "/home/user/project/data"
        """
        self.DATA_PATH = Path(self.DATA_PATH).resolve()
        return self

    @model_validator(mode="after")
    def token_validation(self) -> Self:
        """Validates AniList tokens and Plex users.

        Performs the following validations:
        1. Converts single values to lists for consistency
        2. Ensures equal number of tokens and users

        Returns:
            PlexAnibridgeConfig: Self with validated tokens/users

        Raises:
            ValueError: If token and user counts don't match

        Example:
            Single user:
                ANILIST_TOKEN="token1"
                PLEX_USER="user1"
            Multiple users:
                ANILIST_TOKEN="token1,token2"
                PLEX_USER="user1,user2"
        """
        if isinstance(self.ANILIST_TOKEN, str):
            self.ANILIST_TOKEN = [self.ANILIST_TOKEN]
        if isinstance(self.PLEX_USER, str):
            self.PLEX_USER = [self.PLEX_USER]
        if len(self.ANILIST_TOKEN) != len(self.PLEX_USER):
            raise ValueError("The number of Plex users and AniList tokens must match")
        return self

    def encode(self) -> str:
        """Creates a hash of the configuration for change detection.

        Generates an MD5 hash of sorted configuration values, excluding
        runtime-specific settings (LOG_LEVEL, DRY_RUN, SYNC_INTERVAL).

        Returns:
            str: MD5 hash of the configuration

        Note:
            Used to detect configuration changes between runs for
            determining polling scan eligibility
        """

        def sort_value(value):
            if isinstance(value, (list, set, tuple)):
                return sorted(value)
            elif isinstance(value, dict):
                return {k: sort_value(v) for k, v in sorted(value.items())}
            return value

        config_str = "".join(
            str(sort_value(getattr(self, key)))
            for key in sorted(self.model_fields.keys())
            if key not in ("LOG_LEVEL", "DRY_RUN", "SYNC_INTERVAL")
        )
        return md5(config_str.encode()).hexdigest()

    def __str__(self) -> str:
        """Creates a human-readable representation of the configuration.

        Returns:
            str: Comma-separated list of key-value pairs with sensitive
                 values masked (ANILIST_TOKEN, PLEX_TOKEN)

        Example:
            "PLEX_URL: http://localhost:32400, PLEX_TOKEN: **********, ..."
        """
        secrets = ["ANILIST_TOKEN", "PLEX_TOKEN"]
        return ", ".join(
            [
                f"{key}: {getattr(self, key)}"
                if key not in secrets
                else f"{key}: **********"
                for key in self.model_fields
            ]
        )

    class Config:
        env_file = ".env"
        extra = "ignore"
