from .settings import config as __config
from .logging import setup_logger

log = setup_logger(
    log_name="PlexAniBridge", log_level=__config.LOG_LEVEL, log_dir="logs"
)
