"""PlexAniBridge Configuration Settings."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel
from pydantic.fields import _Unset
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils.logging import get_logger

__all__ = [
    "PlexMetadataSource",
    "SyncField",
    "LogLevel",
    "PlexAnibridgeProfileConfig",
    "PlexAnibridgeConfig",
]

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


class PlexAnibridgeProfileConfig(BaseModel):
    """Configuration for a single PlexAniBridge profile.

    Represents one sync profile with one Plex user and one AniList account.
    """

    anilist_token: str = Field(
        "",
        description="AniList API token for authentication",
    )
    plex_token: str = Field(
        "",
        description="Plex API token for authentication",
    )
    plex_user: str = Field(
        "",
        description="Plex username of target user",
    )
    plex_url: str = Field(
        "",
        description="Plex server URL",
    )
    plex_sections: list[str] = Field(
        default_factory=list,
        description="Library sections to sync (empty = all)",
    )
    plex_genres: list[str] = Field(
        default_factory=list,
        description="Genre filter (empty = all)",
    )
    plex_metadata_source: PlexMetadataSource = Field(
        default=PlexMetadataSource.LOCAL,
        description="Source of metadata for Plex media items",
    )
    sync_interval: int = Field(
        default=3600,
        ge=-1,
        description="Sync interval in seconds (-1 = run once)",
    )
    polling_scan: bool = Field(
        default=False,
        description="Poll for changes every 30 seconds instead of a periodic scan",
    )
    full_scan: bool = Field(
        default=False,
        description="Perform full library scans, even on unwatched items",
    )
    destructive_sync: bool = Field(
        default=False,
        description="Allow decreasing watch progress and removing items from AniList",
    )
    excluded_sync_fields: list[SyncField] = Field(
        default_factory=lambda: [SyncField.NOTES, SyncField.SCORE],
        description="AniList fields to exclude from synchronization",
    )
    dry_run: bool = Field(
        default=False,
        description="Log changes without applying them",
    )
    batch_requests: bool = Field(
        default=False,
        description="Batch AniList API requests for better performance",
    )
    search_fallback_threshold: int = Field(
        default=-1,
        ge=-1,
        le=100,
        description="Fuzzy search threshold",
    )

    _parent: "PlexAnibridgeConfig | None" = None

    @property
    def parent(self) -> "PlexAnibridgeConfig":
        """Get the parent multi-config instance.

        Returns:
            PlexAnibridgeConfig: Parent configuration

        Raises:
            ValueError: If this config is not part of a multi-config
        """
        if not self._parent:
            raise ValueError(
                "This configuration is not part of a multi-config instance"
            )
        return self._parent

    @property
    def data_path(self) -> Path:
        """Get the global data path from parent config."""
        return self.parent.data_path

    @property
    def log_level(self) -> LogLevel:
        """Get the global log level from parent config."""
        return self.parent.log_level

    def validate_required_fields(self) -> "PlexAnibridgeProfileConfig":
        """Validates that required fields are provided.

        Returns:
            PlexAnibridgeProfileConfig: Self with validated fields

        Raises:
            ValueError: If required fields are missing or empty
        """
        if not self.anilist_token:
            raise ValueError("ANILIST_TOKEN is required for each profile")
        if not self.plex_token:
            raise ValueError("PLEX_TOKEN is required for each profile")
        if not self.plex_user:
            raise ValueError("PLEX_USER is required for each profile")
        return self

    def __str__(self) -> str:
        """Creates a human-readable representation of the configuration.

        Returns:
            str: Comma-separated list of key-value pairs with sensitive
                 values masked
        """
        secrets = ["anilist_token", "plex_token"]
        return ", ".join(
            [
                f"{key.upper()}: {getattr(self, key)}"
                if key not in secrets
                else f"{key.upper()}: **********"
                for key in self.__class__.model_fields
                if not key.startswith("_") and getattr(self, key) != _Unset
            ]
        )

    model_config = ConfigDict(extra="forbid")


class PlexAnibridgeConfig(BaseSettings):
    """Multi-configuration manager for PlexAniBridge application.

    Supports loading multiple PlexAniBridge configurations from environment variables
    variables using nested delimiters. Automatically parses
    PAB_PROFILES__${PROFILE_NAME}__${SETTING} format into individual profile
    configurations.

    Global settings are shared across all profiles, while profile-specific settings
    override global defaults.

    Environment Variable Format:
        Global settings:
            PAB_DATA_PATH: Application data directory
            PAB_LOG_LEVEL: Logging level

        Profile settings:
            PAB_PROFILES__${PROFILE_NAME}__ANILIST_TOKEN: AniList token
            PAB_PROFILES__${PROFILE_NAME}__PLEX_TOKEN: Plex token
            PAB_PROFILES__${PROFILE_NAME}__PLEX_USER: Plex username
            ... (all other PlexAnibridgeConfig settings)

    Example:
        PAB_DATA_PATH=/app/data
        PAB_LOG_LEVEL=INFO
        PAB_PROFILES__personal__ANILIST_TOKEN=token1
        PAB_PROFILES__personal__PLEX_TOKEN=plex_token1
        PAB_PROFILES__personal__PLEX_USER=user1
        PAB_PROFILES__family__ANILIST_TOKEN=token2
        PAB_PROFILES__family__PLEX_TOKEN=plex_token2
        PAB_PROFILES__family__PLEX_USER=user2
    """

    def __init__(self, **data) -> None:
        """Initialize the configuration with provided data."""
        super().__init__(**data)
        self._apply_global_defaults()

    profiles: dict[str, PlexAnibridgeProfileConfig] = Field(
        default_factory=dict,
        description="PlexAniBridge profile configurations",
    )

    data_path: Path = Field(
        default=Path("./data"),
        description="Directory for application data",
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Logging level for the application",
    )

    anilist_token: str | None = Field(
        default=None,
        description="Global default AniList API token",
    )
    plex_token: str | None = Field(
        default=None,
        description="Global default Plex API token",
    )
    plex_user: str | None = Field(
        default=None,
        description="Global default Plex username",
    )
    plex_url: str | None = Field(
        default=None,
        description="Global default Plex server URL",
    )
    plex_sections: list[str] | None = Field(
        default=None,
        description="Global default library sections to sync",
    )
    plex_genres: list[str] | None = Field(
        default=None,
        description="Global default genre filter",
    )
    plex_metadata_source: PlexMetadataSource | None = Field(
        default=None,
        description="Global default metadata source",
    )
    sync_interval: int | None = Field(
        default=None,
        ge=-1,
        description="Global default sync interval in seconds",
    )
    polling_scan: bool | None = Field(
        default=None,
        description="Global default polling scan setting",
    )
    full_scan: bool | None = Field(
        default=None,
        description="Global default full scan setting",
    )
    destructive_sync: bool | None = Field(
        default=None,
        description="Global default destructive sync setting",
    )
    excluded_sync_fields: list[SyncField] | None = Field(
        default=None,
        description="Global default excluded sync fields",
    )
    dry_run: bool | None = Field(
        default=None,
        description="Global default dry run setting",
    )
    batch_requests: bool | None = Field(
        default=None,
        description="Global default batch requests setting",
    )
    search_fallback_threshold: int | None = Field(
        default=None,
        ge=-1,
        le=100,
        description="Global default search fallback threshold",
    )

    def _apply_global_defaults(self) -> None:
        """Apply global defaults to all configs and set parent references."""
        # Get all field names that exist in both configs (excluding multi-config fields)
        config_fields = set(PlexAnibridgeProfileConfig.model_fields.keys())
        multi_config_fields = set(self.__class__.model_fields.keys())
        shared_fields = config_fields.intersection(multi_config_fields)

        for config in self.profiles.values():
            config._parent = self

            # Apply global defaults where profile values are not set
            for field_name in shared_fields:
                global_value = getattr(self, field_name)
                config_value = getattr(config, field_name)

                # Apply global default if:
                # 1. Global value is not None
                # 2. Config value is the default or unset
                if global_value is not None and (
                    config_value == _Unset
                    or config_value
                    == PlexAnibridgeProfileConfig.model_fields[field_name].default
                ):
                    setattr(config, field_name, global_value)

            config.validate_required_fields()

    @field_validator("profiles", mode="before")
    @classmethod
    def validate_profiles(cls, v):
        """Validate and convert instantiate PlexAnibridgeProfileConfig instances."""
        if isinstance(v, dict):
            validated_profiles = {}
            for profile_name, config_data in v.items():
                if isinstance(config_data, dict):
                    try:
                        config = PlexAnibridgeProfileConfig(**config_data)
                        validated_profiles[profile_name] = config
                    except Exception as e:
                        _log.error(f"Failed to load profile $$'{profile_name}'$$: {e}")
                        raise ValueError(
                            f"Invalid configuration for profile '{profile_name}': {e}"
                        ) from e
                elif isinstance(config_data, PlexAnibridgeProfileConfig):
                    validated_profiles[profile_name] = config_data
                    _log.info(f"Loaded profile configuration: $$'{profile_name}'$$")
            return validated_profiles
        return v

    @model_validator(mode="after")
    def validate_global_config(self) -> "PlexAnibridgeConfig":
        """Validates global configuration settings.

        Returns:
            PlexAnibridgeConfig: Self with validated settings

        Raises:
            ValueError: If required global settings are missing or invalid
        """
        self.data_path = Path(self.data_path).resolve()  # Ensure data path is absolute

        # If no profiles are provided, try to create a default config from global
        # settings
        if not self.profiles:
            if (
                self.anilist_token
                and self.anilist_token != _Unset
                and self.plex_token
                and self.plex_token != _Unset
                and self.plex_user
                and self.plex_user != _Unset
            ):
                _log.info(
                    f"{self.__class__.__name__}: No profiles configured, creating "
                    f"default profile from global settings"
                )

                default_config_data = {}

                config_fields = set(PlexAnibridgeProfileConfig.model_fields.keys())
                multi_config_fields = set(self.__class__.model_fields.keys())
                shared_fields = config_fields.intersection(multi_config_fields)

                for field_name in shared_fields:
                    global_value = getattr(self, field_name)
                    if global_value is not None:
                        default_config_data[field_name] = global_value

                try:
                    default_config = PlexAnibridgeProfileConfig(**default_config_data)
                    self.profiles["default"] = default_config
                    _log.info(
                        f"{self.__class__.__name__}: Created default profile "
                        "configuration from global settings"
                    )
                except Exception as e:
                    _log.error(
                        f"{self.__class__.__name__}: Failed to create default profile "
                        f"from global settings: {e}"
                    )
                    raise ValueError(
                        f"Invalid global configuration for default profile: {e}"
                    ) from e
            else:
                raise ValueError(
                    "No sync profiles configured and insufficient global settings for "
                    "default profile. Please either:\n1. Set up at least one profile "
                    "using PAB_PROFILES__${PROFILE_NAME}__ANILIST_TOKEN, "
                    "PAB_PROFILES__${PROFILE_NAME}__PLEX_TOKEN, and "
                    "PAB_PROFILES__${PROFILE_NAME}__PLEX_USER, or\n. Provide global "
                    "defaults using PAB_ANILIST_TOKEN, PAB_PLEX_TOKEN, and "
                    "PAB_PLEX_USER"
                )

        return self

    def get_profile_names(self) -> list[str]:
        """Get a list of all configured profile names.

        Returns:
            list[str]: List of profile names
        """
        return list(self.profiles.keys())

    def get_profile(self, name: str) -> PlexAnibridgeProfileConfig:
        """Get a specific profile configuration.

        Args:
            name: Profile name

        Returns:
            PlexAnibridgeProfileConfig: The profile configuration

        Raises:
            KeyError: If profile doesn't exist
        """
        if name not in self.profiles:
            raise KeyError(
                f"Profile '{name}' not found. Available profiles: "
                f"{list(self.profiles.keys())}"
            )
        return self.profiles[name]

    def __str__(self) -> str:
        """Creates a human-readable representation of the configuration.

        Returns:
            str: Configuration summary with profile count and global settings
        """
        profile_count = len(self.profiles)
        profile_names = ", ".join(self.profiles.keys())

        return (
            f"PlexAniBridge Config: {profile_count} profile(s) [{profile_names}], "
            f"DATA_PATH: {self.data_path}, LOG_LEVEL: {self.log_level}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PAB_",
        env_nested_delimiter="__",
        extra="forbid",
    )
