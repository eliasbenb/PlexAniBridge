from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    # General
    SYNC_INTERVAL: Optional[int] = Field(3600, ge=-1)
    PARTIAL_SCAN: Optional[bool] = True
    DESTRUCTIVE_SYNC: Optional[bool] = False

    # Anilist
    ANILIST_TOKEN: str

    # Plex
    PLEX_URL: Optional[str] = "http://localhost:32400"
    PLEX_TOKEN: str
    PLEX_SECTIONS: set[str]

    # Advanced
    DB_PATH: Optional[str] = "db/plexanibridge.db"
    DRY_RUN: Optional[bool] = False
    # in logging.getLevelNamesMapping().keys()
    LOG_LEVEL: Optional[str] = Field(
        "INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"
    )
    FUZZY_SEARCH_THRESHOLD: Optional[int] = Field(90, ge=0, le=100)

    class Config:
        env_file = ".env"

    def __str__(self) -> str:
        secrets = ["ANILIST_TOKEN", "PLEX_TOKEN"]
        return ", ".join(
            [
                f"{key}: {getattr(self, key)}"
                if key not in secrets
                else f"{key}: **********"
                for key in self.model_fields
            ]
        )


config = Config()
