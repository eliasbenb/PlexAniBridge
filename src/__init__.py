from .logging import setup_logger
from .settings import config as __config

log = setup_logger(
    log_name="PlexAniBridge", log_level=__config.LOG_LEVEL, log_dir="logs"
)
