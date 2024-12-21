from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class SyncField(StrEnum):
    """AniList fields that PlexAniBridge is able to sync"""

    STATUS = "status"
    SCORE = "score"
    PROGRESS = "progress"
    REPEAT = "repeat"
    NOTES = "notes"
    STARTED_AT = "started_at"
    COMPLETED_AT = "completed_at"

    def to_camel(self) -> str:
        """ "Converts the enum value to camel case, which is the format AniList uses

        Returns:
            str: The sync field in camel case
        """
        return to_camel(self.value)

    def __repr__(self) -> str:
        """Makes the enum show the value instead of the name when printed

        Returns:
            str: Quoted string of the sync field's value
        """
        return f"'{self.value}'"


class LogLevel(StrEnum):
    """The available logging levels"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __repr__(self) -> str:
        """Makes the enum show the value instead of the name when printed

        Returns:
            str: Quoted string of the log level's value
        """
        return f"'{self.value}'"


class PlexAnibridgeConfig(BaseSettings):
    """Reads, validdates and stores the configuration settings from env vars"""

    # AniList
    ANILIST_TOKEN: str

    # Plex
    PLEX_URL: str = "http://localhost:32400"
    PLEX_TOKEN: str
    PLEX_SECTIONS: set[str]

    # General
    SYNC_INTERVAL: int = Field(3600, ge=-1)
    PARTIAL_SCAN: bool = True
    DESTRUCTIVE_SYNC: bool = False

    EXCLUDED_SYNC_FIELDS: set[SyncField] = {}

    # Advanced
    DATA_PATH: Path = "./data"
    DRY_RUN: bool = False
    LOG_LEVEL: LogLevel = LogLevel.INFO
    FUZZY_SEARCH_THRESHOLD: int = Field(90, ge=0, le=100)

    @model_validator(mode="after")
    def absolute_data_path(self) -> "PlexAnibridgeConfig":
        """Ensures `DATA_PATH` is always absolute"""
        self.DATA_PATH = Path(self.DATA_PATH).resolve()
        return self

    def __str__(self) -> str:
        """Return a string representation of the config

        Used to log the configuration before the program starts

        Returns:
            str: The string representation of the config
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
