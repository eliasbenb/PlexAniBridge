"""PlexAniBridge exception classes."""


class PlexAniBridgeError(Exception):
    """Base class for all PlexAniBridge exceptions."""


# Configuration errors
class ConfigError(PlexAniBridgeError):
    """Base class for configuration-related errors."""


class ProfileConfigError(ConfigError, ValueError):
    """Invalid or incomplete configuration for a specific profile."""


class InvalidMappingsURLError(ConfigError, ValueError):
    """The mappings_url configuration is not a supported HTTP(S) URL or file type."""


class NoProfilesConfiguredError(ConfigError, ValueError):
    """No usable profiles were found in the user's configuration."""


class ProfileNotFoundError(ConfigError, KeyError):
    """Requested profile does not exist."""


class DataPathError(ConfigError, ValueError):
    """The configured data directory path is invalid for the requested operation."""


# Database errors
class DatabaseError(PlexAniBridgeError):
    """Base class for database-related errors."""


class UnsupportedModeError(DatabaseError, ValueError):
    """Unsupported mode value was provided when dumping a database model."""


# Media/model errors
class MediaTypeError(PlexAniBridgeError):
    """Base class for media type related errors."""


class UnsupportedMediaTypeError(MediaTypeError, ValueError):
    """A media object or enum is not one of the supported Plex types."""


# Plex client errors
class PlexError(PlexAniBridgeError):
    """Base class for Plex-related failures."""


class PlexUserNotFoundError(PlexError, ValueError):
    """Unable to resolve the target Plex user among available users."""


class PlexClientNotInitializedError(PlexError, RuntimeError):
    """Operations requiring a Plex user/admin client were attempted too early."""


class InvalidGuidError(PlexError, ValueError):
    """A required Plex GUID was missing or empty."""


# Scheduler errors
class SchedulerError(PlexAniBridgeError):
    """Base class for scheduler-related failures."""


class SchedulerNotInitializedError(SchedulerError, RuntimeError):
    """A scheduler instance is required but not available/initialized."""


class SchedulerUnavailableError(SchedulerError):
    """The scheduler exists but is temporarily unavailable (e.g., shutting down)."""


# Backup/restore errors
class BackupError(PlexAniBridgeError):
    """Base class for backup and restore failures."""


class InvalidBackupFilenameError(BackupError, ValueError):
    """Provided backup filename is invalid or not allowed."""


class BackupFileNotFoundError(BackupError, FileNotFoundError):
    """Expected backup file was not found on disk."""


# History and actions errors
class HistoryError(PlexAniBridgeError):
    """Base class for history-related failures."""


class HistoryItemNotFoundError(HistoryError, KeyError):
    """A requested history entry could not be located."""


# Mappings errors
class MappingError(PlexAniBridgeError):
    """Base class for mapping data source or parsing errors."""


class UnsupportedMappingFileExtensionError(MappingError, ValueError):
    """Provided mappings file path or upload uses an unsupported extension."""


class MissingAnilistIdError(MappingError, ValueError):
    """Operation requires an AniList ID but none was provided."""
