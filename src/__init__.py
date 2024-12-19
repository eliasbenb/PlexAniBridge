from .logging import setup_logger
from .settings import config as __config
from .utils.git_version import get_git_version

log = setup_logger(
    log_name="PlexAniBridge", log_level=__config.LOG_LEVEL, log_dir="logs"
)
__version__ = get_git_version()
