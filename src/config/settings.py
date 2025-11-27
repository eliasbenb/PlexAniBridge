"""AniBridge Configuration Settings."""

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
    ProfileConfigError,
    ProfileNotFoundError,
)
from src.utils.logging import _get_logger

__all__ = [
    "AniBridgeConfig",
    "AniBridgeProfileConfig",
    "LogLevel",
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
    data_path = Path(os.getenv("AB_DATA_PATH", "./data")).resolve()

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
    PROGRESS = "progress"  # Number of episodes/movies watched
    REPEATS = "repeats"  # Number of times rewatched
    REVIEW = "review"  # User's review/comments (text)
    USER_RATING = "user_rating"  # User's rating/score
    STARTED_AT = "started_at"  # When the user started watching (date)
    FINISHED_AT = "finished_at"  # When the user finished watching (date)

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
    webhook: External webhook-triggered syncs, dependent on `ab_web_enabled`
    """

    PERIODIC = "periodic"
    POLL = "poll"
    WEBHOOK = "webhook"


class BasicAuthConfig(BaseModel):
    """Configuration for authentication settings."""

    username: str | None = Field(
        default=None, description="Username for authentication"
    )
    password: SecretStr | None = Field(
        default=None, description="Password for authentication"
    )
    htpasswd_path: Path | None = Field(
        default=None, description="Path to an htpasswd file for authentication"
    )
    realm: str = Field(
        default="AniBridge", description="Realm for HTTP Basic Authentication"
    )


class WebConfig(BaseModel):
    """Configuration for the embedded web server."""

    enabled: bool = Field(default=True, description="Enable the AniBridge web server")
    host: str = Field(default="0.0.0.0", description="Host for the web server")
    port: int = Field(default=4848, description="Port for the web server")
    basic_auth: BasicAuthConfig = Field(
        default_factory=BasicAuthConfig, description="Authentication settings"
    )


class AniBridgeProfileConfig(BaseModel):
    """Configuration for a single AniBridge profile.

    Represents one sync profile with one Plex user and one AniList account.
    """

    library_provider: str = Field(
        default="plex",
        description="Namespace of the library provider to use",
    )
    list_provider: str = Field(
        default="anilist",
        description="Namespace of the list provider to use",
    )
    providers: dict[str, dict] = Field(
        default_factory=dict,
        exclude=True,
        repr=False,
        description="Provider configuration by namespace",
    )

    sync_interval: int = Field(
        default=86400, ge=0, description="Sync interval in seconds"
    )
    sync_modes: list[SyncMode] = Field(
        default_factory=lambda: [SyncMode.PERIODIC, SyncMode.POLL, SyncMode.WEBHOOK],
        description="List of enabled sync modes (periodic, poll, webhook)",
    )
    full_scan: bool = Field(
        default=False, description="Perform full library scans, even on unwatched items"
    )
    destructive_sync: bool = Field(
        default=False,
        description="Allow decreasing watch progress and removing list entries",
    )
    excluded_sync_fields: list[SyncField] = Field(
        default_factory=lambda: [SyncField.REVIEW, SyncField.USER_RATING],
        description="Fields to exclude from synchronization",
    )
    dry_run: bool = Field(
        default=False, description="Log changes without applying them"
    )
    batch_requests: bool = Field(
        default=False, description="Batch API requests for better performance"
    )
    search_fallback_threshold: int = Field(
        default=-1, ge=-1, le=100, description="Fuzzy search threshold"
    )
    backup_retention_days: int = Field(
        default=30,
        ge=0,
        description=("Days to retain list backups before cleanup (0 disables cleanup)"),
    )

    _parent: AniBridgeConfig | None = None

    @property
    def parent(self) -> AniBridgeConfig:
        """Get the parent multi-config instance.

        Returns:
            AniBridgeConfig: Parent configuration

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


class AniBridgeConfig(BaseSettings):
    """Multi-configuration manager for AniBridge application.

    Supports loading multiple AniBridge configurations from environment variables
    variables using nested delimiters. Automatically parses
    AB_PROFILES__${PROFILE_NAME}__${SETTING} format into individual profile
    configurations.

    Global settings are shared across all profiles, while profile-specific settings
    override global defaults.
    """

    # Raw profile data, processed into actual models after global defaults are applied
    raw_profiles: dict[str, dict] = Field(default_factory=dict, exclude=True)
    profiles: dict[str, AniBridgeProfileConfig] = Field(
        default_factory=dict, description="AniBridge profile configurations"
    )

    library_provider: str = Field(
        default="plex", description="Namespace of the library provider to use"
    )
    list_provider: str = Field(
        default="anilist", description="Namespace of the list provider to use"
    )
    provider_modules: list[str] | None = Field(
        default=None,
        description="Additional module paths to load provider implementations from",
    )
    providers: dict[str, dict] = Field(
        default_factory=dict,
        exclude=True,
        repr=False,
        description="Provider configuration by namespace",
    )

    data_path: Path = Field(
        default=Path("./data"), description="Directory for application data"
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO, description="Logging level for the application"
    )
    mappings_url: str | None = Field(
        default="https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/v2/mappings.json",
        description=(
            "URL to JSON or YAML file to use as the upstream mappings source. "
            "If not set, no upstream mappings will be used."
        ),
    )
    web: WebConfig = Field(
        default_factory=WebConfig, description="Embedded web server configuration"
    )

    sync_interval: int | None = Field(
        default=None, ge=0, description="Global default sync interval in seconds"
    )
    sync_modes: list[SyncMode] | None = Field(
        default=None, description="Global default list of sync modes"
    )
    full_scan: bool | None = Field(
        default=None, description="Global default full scan setting"
    )
    destructive_sync: bool | None = Field(
        default=None, description="Global default destructive sync setting"
    )
    excluded_sync_fields: list[SyncField] | None = Field(
        default=None, description="Global default excluded sync fields"
    )
    dry_run: bool | None = Field(
        default=None, description="Global default dry run setting"
    )
    batch_requests: bool | None = Field(
        default=None, description="Global default batch requests setting"
    )
    search_fallback_threshold: int | None = Field(
        default=None,
        ge=-1,
        le=100,
        description="Global default search fallback threshold",
    )
    backup_retention_days: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Global default backup retention period in days (0 disables cleanup)"
        ),
    )

    @staticmethod
    def _shared_profile_fields() -> set[str]:
        """Compute field names present in both the global and per-profile models."""
        return set(AniBridgeProfileConfig.model_fields).intersection(
            AniBridgeConfig.model_fields
        )

    def _apply_global_defaults(self) -> None:
        """Apply global defaults and instantiate profile configs from raw profiles."""
        shared_fields = self._shared_profile_fields()
        for profile_name, raw_config in self.raw_profiles.items():
            config_data = raw_config.copy()
            for field_name in shared_fields:
                # Special-case merging for nested provider settings: we want to
                # preserve per-profile overrides while inheriting unspecified
                # values from global provider definitions.
                if field_name == "providers":
                    global_value = getattr(self, field_name) or {}
                    profile_value = config_data.get(field_name) or {}
                    merged_providers = {}
                    # start with global providers
                    for ns, cfg in (global_value or {}).items():
                        merged_providers[ns] = (
                            cfg.copy() if isinstance(cfg, dict) else cfg
                        )
                    # merge profile providers, overriding global keys
                    for ns, cfg in (profile_value or {}).items():
                        existing = merged_providers.get(ns, {})
                        if isinstance(existing, dict) and isinstance(cfg, dict):
                            merged = existing.copy()
                            merged.update(cfg)
                            merged_providers[ns] = merged
                        else:
                            merged_providers[ns] = cfg
                    if merged_providers:
                        config_data[field_name] = merged_providers
                else:
                    if field_name not in config_data:
                        global_value = getattr(self, field_name)
                        if global_value is not None:
                            config_data[field_name] = global_value
            try:
                profile = AniBridgeProfileConfig(**config_data)
                profile._parent = self
                self.profiles[profile_name] = profile
            except Exception as exc:
                _log.error(f"Failed to create profile '{profile_name}': {exc}")
                raise ProfileConfigError(
                    f"Invalid configuration for profile '{profile_name}': {exc}"
                ) from exc

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
        if isinstance(values, dict) and "profiles" in values:
            raw_profiles = values.get("profiles", {})
            if isinstance(raw_profiles, dict):
                # Store raw profile data and clear the profiles field
                values["raw_profiles"] = raw_profiles
                values["profiles"] = {}
        return values

    @model_validator(mode="after")
    def validate_global_config(self) -> AniBridgeConfig:
        """Validates global configuration settings.

        Returns:
            AniBridgeConfig: Self with validated settings

        Raises:
            ValueError: If required global settings are missing or invalid
        """
        self.data_path = Path(self.data_path).resolve()

        # If there are no explicit profiles, attempt to bootstrap a default from globals
        if not self.raw_profiles and not self.profiles:
            _log.info(
                "No profiles configured; creating implicit 'default' profile from "
                "globals"
            )
            default_config = {}
            for field_name in self._shared_profile_fields():
                value = getattr(self, field_name)
                if value is not None:
                    default_config[field_name] = value
            self.raw_profiles["default"] = default_config

        if (not self.web.basic_auth.username) != (not self.web.basic_auth.password):
            _log.warning(
                "Both web.basic_auth.username and web.basic_auth.password must be set "
                "to enable static HTTP Basic Authentication credentials; ignoring "
                "partial values"
            )
            self.web.basic_auth.username = None
            self.web.basic_auth.password = None

        if (
            self.web.basic_auth.htpasswd_path
            and not self.web.basic_auth.htpasswd_path.is_file()
        ):
            raise ValueError(
                "web.basic_auth.htpasswd_path must point to an existing file"
            )

        self._apply_global_defaults()
        return self

    def get_profile(self, name: str) -> AniBridgeProfileConfig:
        """Get a specific profile configuration.

        Args:
            name: Profile name

        Returns:
            AniBridgeProfileConfig: The profile configuration

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
            f"AniBridge Config: {profile_count} profile(s) [{profile_names}], "
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
                env_prefix="AB_",
                env_nested_delimiter="__",
                env_parse_none_str="null",
            ),
            DotEnvSettingsSource(
                settings_cls,
                env_file=".env",
                env_prefix="AB_",
                env_nested_delimiter="__",
                env_parse_none_str="null",
            ),
            YamlConfigSettingsSource(settings_cls, yaml_file=find_yaml_config_file()),
        )

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


@lru_cache(maxsize=1)
def get_config() -> AniBridgeConfig:
    """Get the singleton instance of AniBridgeConfig.

    Returns:
        AniBridgeConfig: The singleton configuration instance
    """
    return AniBridgeConfig()
