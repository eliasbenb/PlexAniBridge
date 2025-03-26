import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorama
from colorama import Fore, Style

from src.utils.terminal import supports_color


class ColorFormatter(logging.Formatter):
    """Custom formatter that adds terminal colors to log messages.

    Enhances log readability by adding color coding to different components:
    - Log levels are colored according to severity
    - Quoted strings are highlighted in light blue
    - Curly brace values are dimmed

    Color Scheme:
        DEBUG: Cyan
        INFO: Green
        SUCCESS: Light Cyan
        WARNING: Yellow
        ERROR: Red
        CRITICAL: Bright Red
        Quoted values: Light Blue (e.g., $$'example'$$)
        Bracketed values: Dimmed (e.g., $${key: value}$$)
    """

    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "SUCCESS": Fore.GREEN + Style.BRIGHT,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Formats a log record with ANSI color codes.

        Args:
            record (logging.LogRecord): Log record to format

        Returns:
            str: Color-formatted log message
        """
        orig_msg = record.msg
        orig_levelname = record.levelname
        record.levelname = f"{self.COLORS.get(record.levelname, '')}{record.levelname}{Style.RESET_ALL}"

        if isinstance(record.msg, str):
            # Color strings in quotes
            record.msg = re.sub(
                r"\$\$'((?:[^']|'(?!\$\$))*)'\$\$",
                f"{Fore.LIGHTBLUE_EX}'\\1'{Style.RESET_ALL}",
                record.msg,
            )
            # Color curly brace values
            record.msg = re.sub(
                r"\$\$\{(.*?)\}\$\$",
                f"{Style.DIM}{{\\1}}{Style.RESET_ALL}",
                record.msg,
            )

        result = super().format(record)

        record.levelname = orig_levelname
        record.msg = orig_msg

        return result


class CleanFormatter(logging.Formatter):
    """Formatter that strips color markers from log messages.

    Used for file output where color codes are unnecessary and would
    reduce readability. Removes the special markers while preserving
    the content within them.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Formats a log record by removing color markers.

        Args:
            record (logging.LogRecord): Log record to format

        Returns:
            str: Clean log message without color markers

        """
        if isinstance(record.msg, str):
            orig_msg = record.msg

            # Remove the $$ markers and keep the content
            cleaned_msg = re.sub(r"\$\$\'(.*?)\'\$\$", "'\\1'", record.msg)
            cleaned_msg = re.sub(r"\$\$\{(.*?)\}\$\$", "{\\1}", cleaned_msg)
            record.msg = cleaned_msg

            result = super().format(record)

            record.msg = orig_msg

            return result

        return super().format(record)


class Logger(logging.Logger):
    """Extended Logger class with additional log levels and color support."""

    SUCCESS = logging.INFO + 5

    def __init__(self, name, level=logging.NOTSET):
        """Initialize the enhanced logger.

        Args:
            name (str): Logger name
            level (int, optional): Initial logging level. Defaults to NOTSET.
        """
        super().__init__(name, level)

        if not hasattr(logging, "SUCCESS"):
            logging.addLevelName(self.SUCCESS, "SUCCESS")

    def success(self, msg, *args, **kwargs):
        """Log a message with SUCCESS level.

        Args:
            msg: Message to log
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments
        """
        if self.isEnabledFor(self.SUCCESS):
            self._log(self.SUCCESS, msg, args, **kwargs)

    def setup(self, log_level: str, log_dir: str) -> None:
        """Configure the logger with console and file output.

        Creates a logger that writes to both console (with colors) and a rotating
        log file (without colors). The log format varies based on log level.

        Args:
            log_level (str): Logging level ('DEBUG', 'INFO', 'SUCCESS', etc.)
            log_dir (str): Directory where log files will be stored
        """
        has_color_support = False
        if supports_color():
            try:
                if sys.platform == "win32":
                    colorama.just_fix_windows_console()
                else:
                    colorama.init()
                has_color_support = True
            except (AttributeError, ImportError, OSError):
                has_color_support = False

        if log_level == "SUCCESS":
            log_level_literal = self.SUCCESS
        else:
            log_level_literal = getattr(logging, log_level)

        self.setLevel(log_level_literal)

        for handler in self.handlers[:]:
            self.removeHandler(handler)

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        log_format = (
            "%(asctime)s - %(name)s - %(levelname)s\t%(filename)s:%(lineno)d\t%(message)s"
            if log_level_literal <= logging.DEBUG
            else "%(asctime)s - %(name)s - %(levelname)s\t%(message)s"
        )

        file_formatter = CleanFormatter(
            log_format,
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_formatter = (
            ColorFormatter(
                log_format,
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            if has_color_support
            else CleanFormatter(
                log_format,
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

        log_file = log_path / f"{self.name}.{log_level}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(log_level_literal)
        self.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(log_level_literal)
        self.addHandler(console_handler)


logging.setLoggerClass(Logger)


def get_logger(log_name: str, log_level: str = "INFO", log_dir: str = "logs") -> Logger:
    """Get a configured instance of Logger.

    Args:
        log_name (str): Name of the logger and base name for log file
        log_level (str, optional): Logging level. Defaults to "INFO".
        log_dir (str, optional): Directory where log files will be stored. Defaults to "logs".

    Returns:
        Logger: Configured logger instance
    """
    logger = logging.getLogger(log_name)

    if isinstance(logger, Logger):
        logger.setup(log_level, log_dir)
    else:
        logger = Logger(log_name)
        logger.setup(log_level, log_dir)

    return logger
