from typing import Optional

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    # General
    LOG_LEVEL: str = "INFO"
    DB_PATH: str = "plexanibridge.db"

    # Anilist
    ANILIST_TOKEN: str
    ANILIST_USER: str

    # Plex
    PLEX_URL: Optional[str] = "http://localhost:32400"
    PLEX_TOKEN: str
    PLEX_SECTIONS: list[str]
    PLEX_USER: str

    # Advanced
    FUZZY_SEARCH_THRESHOLD: Optional[int] = 90

    class Config:
        env_file = ".env"


config = Config()
