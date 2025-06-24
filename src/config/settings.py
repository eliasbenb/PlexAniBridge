from enum import StrEnum
from hashlib import md5
from pathlib import Path

from pydantic import Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic.fields import _Unset
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils.logging import get_logger

__all__ = ["PlexMetadataSource", "SyncField", "LogLevel", "PlexAnibridgeConfig"]

_log = get_logger(log_name="PlexAniBridge", log_level="INFO")


class BaseStrEnum(StrEnum):
    """Base class for string-based enumerations with a custom __repr__ method.

    Provides case-insensitive lookup functionality and consistent string
    representation for enumeration values.
    """

    @classmethod
    def _missing_(cls, value: object) -> "BaseStrEnum | None":
        """Handle case-insensitive lookup for enum values.

        Args:
            value: The value to look up in the enumeration

        Returns:
            BaseStrEnum | None: The matching enum member if found, None otherwise
        """
        value = value.lower() if isinstance(value, str) else value
        for member in cls:
            if member.lower() == value:
                return member
        return None

    def __repr__(self) -> str:
        """Return the string value of the enum member."""
        return self.value

    def __str__(self) -> str:
        """Return the string representation of the enum member."""
        return repr(self)


class PlexMetadataSource(BaseStrEnum):
    """Defines the source of metadata for Plex media items."""

    LOCAL = "local"  # Metadata is sourced from the local Plex server
    ONLINE = "online"  # Metadata is sourced from Plex's online services


class LogLevel(BaseStrEnum):
    """Enumeration of available logging levels.

    Standard Python logging levels used to control log output verbosity.
    Ordered from most verbose (DEBUG) to least verbose (CRITICAL).

    Note: SUCCESS is a custom level used by this application.
    """

    DEBUG = "DEBUG"  # Detailed information for debugging
    INFO = "INFO"  # General information about program execution
    SUCCESS = "SUCCESS"  # Successful operations (custom level)
    WARNING = "WARNING"  # Potential problems or issues
    ERROR = "ERROR"  # Error that prevented an operation
    CRITICAL = "CRITICAL"  # Error that prevents further program execution


class SyncField(BaseStrEnum):
    """Enumeration of AniList fields that can be synchronized with Plex.

    These fields represent the data that can be synchronized between Plex
    and AniList for each media entry. Each enum value corresponds to an
    AniList API field name in snake_case format.
    """

    STATUS = "status"  # Watch status (watching, completed, etc.)
    SCORE = "score"  # User rating (0-100 or 0-10 depending on user settings)
    PROGRESS = "progress"  # Number of episodes/movies watched
    REPEAT = "repeat"  # Number of times rewatched
    NOTES = "notes"  # User's notes/comments
    STARTED_AT = "started_at"  # When the user started watching (date)
    COMPLETED_AT = "completed_at"  # When the user finished watching (date)

    def to_camel(self) -> str:
        """Convert the field name to camelCase for AniList API compatibility.

        Returns:
            str: The field name in camelCase format

        Examples:
            >>> SyncField.STARTED_AT.to_camel()
            'startedAt'
            >>> SyncField.STATUS.to_camel()
            'status'
        """
        return to_camel(self.value)


class PlexAnibridgeConfig(BaseSettings):
    """Configuration manager for PlexAniBridge application.

    Handles loading, validation, and storage of configuration settings from
    environment variables or .env file. Provides type checking and validation
    rules for all settings.

    Settings are loaded in the following order of precedence:
    1. Environment variables
    2. .env file
    3. Default values
    """

    # AniList Configuration
    ANILIST_TOKEN: str | list[str] = _Unset

    # Plex Configuration
    PLEX_TOKEN: str = _Unset
    PLEX_USER: str | list[str] = _Unset
    PLEX_URL: str = "http://localhost:32400"
    PLEX_SECTIONS: list[str] = []  # Library sections to sync (empty = all)
    PLEX_GENRES: list[str] = []  # Genre filter (empty = all genres)
    PLEX_METADATA_SOURCE: PlexMetadataSource = PlexMetadataSource.LOCAL

    # Synchronization Settings
    SYNC_INTERVAL: int = Field(default=3600, ge=-1)  # Seconds (-1 = run once)
    POLLING_SCAN: bool = False  # Use polling instead of webhooks
    FULL_SCAN: bool = False  # Perform full library scan on startup
    DESTRUCTIVE_SYNC: bool = False  # Allow removing items from AniList
    EXCLUDED_SYNC_FIELDS: list[SyncField] = [SyncField.NOTES, SyncField.SCORE]

    # Advanced Configuration
    DATA_PATH: Path = Path("./data")  # Directory for application data
    DRY_RUN: bool = False  # Preview changes without applying them
    LOG_LEVEL: LogLevel = LogLevel.INFO
    BATCH_REQUESTS: bool = False  # Batch API requests for better performance
    SEARCH_FALLBACK_THRESHOLD: int = Field(
        default=-1, ge=-1, le=100
    )  # Fuzzy search threshold

    @model_validator(mode="before")
    def catch_extra_env_vars(cls, values) -> dict[str, str]:
        """Catches extra environment variables not defined in the model and logs them."""
        # `DEPRECATED` and `DEPRECATED_ALIAS` are used to warn users about
        # upcoming changes to configuration settings.
        DEPRECATED: dict[str, str] = {}
        # `DEPRECATED_ALIAS` allows for deprecated settings to be (temporarily)
        # aliased to new settings to ease the transition.
        DEPRECATED_ALIAS: dict[str, str] = {
            "FUZZY_SEARCH_THRESHOLD": "SEARCH_FALLBACK_THRESHOLD"
        }

        wanted: set[str] = set(cls.model_fields.keys())
        extra: set[str] = set(values.keys()) - wanted

        for key in extra:
            key = key.upper()
            if key in DEPRECATED:
                _log.warning(
                    f"$$'{key}'$$ is going to become deprecated soon, use $$'{DEPRECATED[key]}'$$ instead"
                )
            elif key in DEPRECATED_ALIAS:
                _log.warning(
                    f"$$'{key}'$$ is going to become deprecated soon, use $$'{DEPRECATED_ALIAS[key]}'$$ instead"
                )
                values[DEPRECATED_ALIAS[key]] = values[key.lower()]
            else:
                _log.warning(f"Unrecognized configuration setting: $$'{key}'$$")
            del values[key.lower()]

        return values

    @model_validator(mode="after")
    def absolute_data_path(self) -> "PlexAnibridgeConfig":
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
    def token_validation(self) -> "PlexAnibridgeConfig":
        """Validates AniList tokens and Plex users.

        Performs the following validations:
        1. Converts single values to lists for consistency
        2. Ensures equal number of tokens and users

        Returns:
            PlexAnibridgeConfig: Self with validated tokens/users

        Raises:
            ValueError: If token and user counts don't match
        """
        if isinstance(self.ANILIST_TOKEN, str):
            self.ANILIST_TOKEN = [self.ANILIST_TOKEN]
        if isinstance(self.PLEX_USER, str):
            self.PLEX_USER = [self.PLEX_USER]
        if len(self.ANILIST_TOKEN) != len(self.PLEX_USER):
            raise ValueError("The number of Plex users and AniList tokens must match")
        if any(not token for token in self.ANILIST_TOKEN):
            raise ValueError("AniList tokens cannot be empty")
        if any(not user for user in self.PLEX_USER):
            raise ValueError("Plex users cannot be empty")
        return self

    def encode(self) -> str:
        """Creates a hash of the configuration for change detection.

        Generates an MD5 hash of sorted configuration values, excluding
        runtime-specific settings (LOG_LEVEL, DRY_RUN, SYNC_INTERVAL).

        Returns:
            str: MD5 hash of the configuration
        """

        def sort_value(value):
            if isinstance(value, (list, set, tuple)):
                return sorted(value)
            elif isinstance(value, dict):
                return {k: sort_value(v) for k, v in sorted(value.items())}
            return value

        # We exclude certain 'inconsequential' fields from the hash to avoid
        # unnecessary restarts of the application when they change.
        config_str = "".join(
            str(sort_value(getattr(self, key)))
            for key in sorted(self.__class__.model_fields.keys())
            if key not in ("LOG_LEVEL", "DRY_RUN", "SYNC_INTERVAL")
        )
        return md5(config_str.encode()).hexdigest()

    def __str__(self) -> str:
        """Creates a human-readable representation of the configuration.

        Returns:
            str: Comma-separated list of key-value pairs with sensitive
                 values masked (ANILIST_TOKEN, PLEX_TOKEN)
        """
        secrets = ["ANILIST_TOKEN", "PLEX_TOKEN"]
        return ", ".join(
            [
                f"{key}: {getattr(self, key)}"
                if key not in secrets
                else f"{key}: **********"
                for key in self.__class__.model_fields
            ]
        )

    model_config = SettingsConfigDict(env_file=".env", extra="allow")
