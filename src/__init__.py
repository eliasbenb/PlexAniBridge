from .logging import Logger, get_logger
from .settings import PlexAnibridgeConfig
from .utils.version import get_git_hash, get_pyproject_version

__author__ = "Elias Benbourenane <eliasbenbourenane@gmail.com>"
__credits__ = ["eliasbenb"]
__license__ = "MIT"
__maintainer__ = "eliasbenb"
__email__ = "eliasbenbourenane@gmail.com"
__version__ = get_pyproject_version()
__git_hash__ = get_git_hash()

PLEXANIBDRIGE_HEADER = f"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                           P L E X A N I B R I D G E                           ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Version: {__version__:<68}║
║  Git Hash: {__git_hash__:<67}║
║  Author: {f"{__author__} @{__maintainer__}":<69}║
║  License: {__license__:<68}║
║  Repository: https://github.com/eliasbenb/PlexAniBridge                       ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
""".strip()

config = PlexAnibridgeConfig()

log: Logger = get_logger(
    log_name="PlexAniBridge", log_level=config.LOG_LEVEL, log_dir="logs"
)
