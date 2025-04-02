import os
import uuid

from .logging import Logger, get_logger
from .settings import PlexAnibridgeConfig
from .utils.terminal import supports_utf8
from .utils.version import get_docker_status, get_git_hash, get_pyproject_version

__author__ = "Elias Benbourenane <eliasbenbourenane@gmail.com>"
__credits__ = ["eliasbenb"]
__license__ = "MIT"
__maintainer__ = "eliasbenb"
__email__ = "eliasbenbourenane@gmail.com"
__version__ = get_pyproject_version()
__git_hash__ = get_git_hash()


if supports_utf8():
    PLEXANIBDRIGE_HEADER = f"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                           P L E X A N I B R I D G E                           ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Version: {__version__:<68}║
║  Git Hash: {__git_hash__:<67}║
║  Docker: {"Yes" if get_docker_status() else "No":<69}║
║  Author: {f"{__author__} @{__maintainer__}":<69}║
║  License: {__license__:<68}║
║  Repository: https://github.com/eliasbenb/PlexAniBridge                       ║
║  Documentation: https://plexanibridge.elias.eu.org                            ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
    """.strip()
else:
    PLEXANIBDRIGE_HEADER = f"""
+-------------------------------------------------------------------------------+
|                           P L E X A N I B R I D G E                           |
+-------------------------------------------------------------------------------+
|                                                                               |
|  Version: {__version__:<68}|
|  Git Hash: {__git_hash__:<67}|
|  Docker: {"Yes" if get_docker_status() else "No":<69}|
|  Author: {f"{__author__} @{__maintainer__}":<69}|
|  License: {__license__:<68}|
|  Repository: https://github.com/eliasbenb/PlexAniBridge                       |
|  Documentation: https://plexanibridge.elias.eu.org                            |
|                                                                               |
+-------------------------------------------------------------------------------+
    """.strip()

config = PlexAnibridgeConfig()

log: Logger = get_logger(
    log_name="PlexAniBridge",
    log_level=config.LOG_LEVEL,
    log_dir=str(config.DATA_PATH / "logs"),
)

# The below environment variables are consumed by the python-plexapi library
# and are used to identify the client making the requests to the Plex server.
# Having a consistent identifier is important so that the server doesn't think
# the client is a new one every time it starts (which causes "New Device"
# notifications)
os.environ["PLEXAPI_HEADER_IDENTIFIER"] = uuid.uuid3(
    uuid.NAMESPACE_DNS, "PlexAniBridge"
).hex
os.environ["PLEXAPI_HEADER_DEVICE_NAME"] = "PlexAniBridge"
os.environ["PLEXAPI_HEADER_VERSION"] = __version__
os.environ["PLEXAPI_HEADER_PROVIDES"] = ""
