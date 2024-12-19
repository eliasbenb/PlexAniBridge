from .logging import setup_logger
from .settings import config as __config
from .utils.version import get_git_hash, get_pyproject_version

__author__ = "Elias Benbourenane <eliasbenbourenane@gmail.com>"
__credits__ = ["eliasbenb"]
__license__ = "MIT"
__maintainer__ = "eliasbenb"
__email__ = "eliasbenbourenane@gmail.com"
__version__ = get_pyproject_version()
__git_hash__ = get_git_hash()

log = setup_logger(
    log_name="PlexAniBridge", log_level=__config.LOG_LEVEL, log_dir="logs"
)
