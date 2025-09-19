"""PlexAniBridge Configuration Settings."""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from src.exceptions import (
    InvalidMappingsURLError,
    NoProfilesConfiguredError,
    ProfileConfigError,
    ProfileNotFoundError,
)
from src.utils.logging import _get_logger

__all__ = [
    "LogLevel",
    "PlexAnibridgeConfig",
    "PlexAnibridgeProfileConfig",
    "PlexMetadataSource",
    "SyncField",
    "SyncMode",
    "get_config",
]

_log = _get_logger(__name__)


def find_yaml_config_file() -> Path | None:
    """Find the YAML configuration file in the data path.

    Returns:
        Path | None: The path to the YAML configuration file
    """
    data_path = Path(os.getenv("PAB_DATA_PATH", "./data")).resolve()

    for location in [data_path, Path(".")]:
        for ext in ["yaml", "yml"]:
            yaml_file = location / f"config.{ext}"
            if yaml_file.exists():
                _log.debug(f"Using YAML config file: {yaml_file.resolve()}")
                return yaml_file.resolve()
    return None


class BaseStrEnum(StrEnum):
    """Base class for string-based enumerations with a custom __repr__ method.

    Provides case-insensitive lookup functionality and consistent string
    representation for enumeration values.
    """

    @classmethod
    def _missing_(cls, value: object) -> BaseStrEnum | None:
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


class SyncMode(BaseStrEnum):
    """Synchronization execution modes.

    Multiple modes can be enabled simultaneously by specifying a list.

    periodic: Periodic scans every `sync_interval` seconds
    poll: Poll for incremental changes every 30 seconds
    webhook: External webhook-triggered syncs, dependent on `pab_web_enabled`
    """

    PERIODIC = "periodic"
    POLL = "poll"
    WEBHOOK = "webhook"


def _apply_deprecations(data: dict) -> dict:
    """Translate deprecated/legacy configuration fields in-place.

    Central location for all migrations of removed/renamed settings so the
    logic does not become duplicated across validators / constructors.

    Args:
        data: Raw configuration mapping

    Returns:
        dict: Same mapping
    """
    if not isinstance(data, dict):
        return data
    if "polling_scan" in data:
        _log.warning(
            "The 'polling_scan' setting is deprecated and will be removed in the future"
        )
        if "sync_modes" not in data:
            polling_val = data.pop("polling_scan")
            if polling_val:
                data["sync_modes"] = [SyncMode.POLL]
    return data


class PlexAnibridgeProfileConfig(BaseModel):
    """Configuration for a single PlexAniBridge profile.

    Represents one sync profile with one Plex user and one AniList account.
    """

    anilist_token: SecretStr = Field(
        ...,
        description="AniList API token for authentication",
    )
    plex_token: SecretStr = Field(
        ...,
        description="Plex API token for authentication",
    )
    plex_user: str = Field(
        ...,
        description="Plex username of target user",
    )
    plex_url: str = Field(
        default=...,
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
        ge=0,
        description="Sync interval in seconds",
    )
    sync_modes: list[SyncMode] = Field(
        default_factory=lambda: [SyncMode.PERIODIC],
        description="List of enabled sync modes (periodic, poll, webhook)",
    )
    polling_scan: bool | None = Field(
        default=None,
        deprecated="Use sync_modes list instead; True maps to ['poll']",
        exclude=True,
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

    _parent: PlexAnibridgeConfig | None = None

    @property
    def parent(self) -> PlexAnibridgeConfig:
        """Get the parent multi-config instance.

        Returns:
            PlexAnibridgeConfig: Parent configuration

        Raises:
            ProfileConfigError: If this config is not part of a multi-config
        """
        if not self._parent:
            raise ProfileConfigError(
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

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _translate_deprecated(cls, values):
        """Apply centralized deprecated field translations for profile configs."""
        return _apply_deprecations(values)


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
            PAB_PROFILES__${PROFILE_NAME}__PLEX_URL: Plex server URL
            ... (all other PlexAnibridgeConfig settings)

    Example:
        PAB_DATA_PATH=/app/data
        PAB_LOG_LEVEL=INFO
        PAB_PROFILES__personal__ANILIST_TOKEN=token1
        PAB_PROFILES__personal__PLEX_TOKEN=plex_token1
        PAB_PROFILES__personal__PLEX_USER=user1
        PAB_PROFILES__personal__PLEX_URL=http://plex_url1
        PAB_PROFILES__family__ANILIST_TOKEN=token2
        PAB_PROFILES__family__PLEX_TOKEN=plex_token2
        PAB_PROFILES__family__PLEX_USER=user2
        PAB_PROFILES__family__PLEX_URL=http://plex_url2
    """

    def __init__(self, **data) -> None:
        """Initialize the configuration with provided data."""
        _apply_deprecations(data)
        super().__init__(**data)
        self._apply_global_defaults()

    # Store raw profile data until after global defaults are applied
    raw_profiles: dict[str, dict] = Field(
        default_factory=dict,
        description="Raw profile data before instantiation",
        exclude=True,
    )

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
    mappings_url: str | None = Field(
        default="https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/v2/mappings.json",
        description=(
            "URL to JSON or YAML file to use as the upstream mappings source. "
            "If not set, no upstream mappings will be used."
        ),
    )
    web_enabled: bool = Field(
        default=True,
        description="Enable embedded FastAPI web UI server",
    )
    web_host: str = Field(
        default="0.0.0.0",
        description="Web server listen host",
    )
    web_port: int = Field(
        default=4848,
        description="Web server listen port",
    )

    anilist_token: SecretStr | None = Field(
        default=None,
        description="Global default AniList API token",
    )
    plex_token: SecretStr | None = Field(
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
        ge=0,
        description="Global default sync interval in seconds",
    )
    sync_modes: list[SyncMode] | None = Field(
        default=None,
        description="Global default list of sync modes",
    )
    polling_scan: bool | None = Field(
        default=None,
        deprecated="Use sync_modes list instead; True maps to ['poll']",
        exclude=True,
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

    @staticmethod
    def _shared_profile_fields() -> set[str]:
        """Compute field names present in both the global and per-profile models."""
        return set(PlexAnibridgeProfileConfig.model_fields).intersection(
            PlexAnibridgeConfig.model_fields
        )

    def _apply_global_defaults(self) -> None:
        """Apply global defaults and instantiate profile configs from raw profiles."""
        shared_fields = self._shared_profile_fields()
        for profile_name, raw_config in self.raw_profiles.items():
            config_data = _apply_deprecations(raw_config.copy())
            for field_name in shared_fields:
                if field_name not in config_data:
                    global_value = getattr(self, field_name)
                    if global_value is not None:
                        config_data[field_name] = global_value
            try:
                profile = PlexAnibridgeProfileConfig(**config_data)
                profile._parent = self
                self.profiles[profile_name] = profile
            except Exception as e:
                _log.error(
                    f"{self.__class__.__name__}: Failed to create profile "
                    f"$$'{profile_name}'$$: {e}"
                )
                raise ProfileConfigError(
                    f"Invalid configuration for profile '{profile_name}': {e}"
                ) from e

    @field_validator("mappings_url")
    @classmethod
    def validate_mappings_url(cls, v: str | None) -> str | None:
        """Validate the mappings_url field format."""
        if not v:
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise InvalidMappingsURLError(
                "mappings_url must start with http:// or https://"
            )
        if not (v.endswith(".json") or v.endswith(".yaml") or v.endswith(".yml")):
            raise InvalidMappingsURLError(
                "mappings_url must point to a .json, .yaml, or .yml file"
            )
        return v

    @field_validator("profiles", mode="before")
    @classmethod
    def validate_profiles(cls, v, values=None):
        """Store raw profile data for later instantiation."""
        if isinstance(v, dict):
            # Don't create instances yet, just store the raw data
            # This will be processed in _apply_global_defaults
            return {}  # Return empty dict, we'll populate it later
        return v

    @model_validator(mode="before")
    @classmethod
    def extract_raw_profiles(cls, values):
        """Extract raw profile data before main validation."""
        values = _apply_deprecations(values)
        if isinstance(values, dict) and "profiles" in values:
            raw_profiles = values.get("profiles", {})
            if isinstance(raw_profiles, dict):
                # Store raw profile data and clear the profiles field
                values["raw_profiles"] = raw_profiles
                values["profiles"] = {}
        return values

    @model_validator(mode="after")
    def validate_global_config(self) -> PlexAnibridgeConfig:
        """Validates global configuration settings.

        Returns:
            PlexAnibridgeConfig: Self with validated settings

        Raises:
            ValueError: If required global settings are missing or invalid
        """
        self.data_path = Path(self.data_path).resolve()

        # If there are no explicit profiles, attempt to bootstrap a default from globals
        if not self.raw_profiles and not self.profiles:
            if self.anilist_token and self.plex_token and self.plex_user:
                _log.info(
                    f"{self.__class__.__name__}: No profiles configured; "
                    "creating implicit 'default' profile from globals"
                )
                default_config = {}
                for field_name in self._shared_profile_fields():
                    value = getattr(self, field_name)
                    if value is not None:
                        default_config[field_name] = value
                self.raw_profiles["default"] = default_config
            else:
                raise NoProfilesConfiguredError(
                    "No sufficiently populated sync profiles are configured. Either "
                    "define at least one profile via PAB_PROFILES__${PROFILE}__* or "
                    "set global PAB_ANILIST_TOKEN, PAB_PLEX_TOKEN, PAB_PLEX_USER, and "
                    "PAB_PLEX_URL."
                )

        return self

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
            raise ProfileNotFoundError(
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customizes the settings sources for the configuration.

        Order of precedence:
        1. Environment variables
        2. .env file in the CWD
        3. YAML configuration file in the data path
        """
        return (
            EnvSettingsSource(
                settings_cls,
                env_prefix="PAB_",
                env_nested_delimiter="__",
            ),
            DotEnvSettingsSource(
                settings_cls,
                env_file=".env",
                env_prefix="PAB_",
                env_nested_delimiter="__",
            ),
            YamlConfigSettingsSource(
                settings_cls,
                yaml_file=find_yaml_config_file(),
            ),
        )

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="forbid",
    )


@lru_cache(maxsize=1)
def get_config() -> PlexAnibridgeConfig:
    """Get the singleton instance of PlexAnibridgeConfig.

    Returns:
        PlexAnibridgeConfig: The singleton configuration instance
    """
    return PlexAnibridgeConfig()
