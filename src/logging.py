import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorama
from colorama import Fore, Style


def add_logging_level(level_name, level_num, method_name=None):
    """
    Comprehensively adds a new logging level to the `logging` module and the
    currently configured logging class.

    Args:
        level_name (str): Name of the level (e.g., 'SUCCESS')
        level_num (int): Numeric value for the level (e.g., logging.DEBUG - 5)
        method_name (str, optional): Name of the method to add to Logger class.
                                    Defaults to level_name.lower().

    Raises:
        AttributeError: If the level or method name already exists in logging
    """
    if not method_name:
        method_name = level_name.lower()

    if hasattr(logging, level_name):
        raise AttributeError(f"{level_name} already defined in logging module")
    if hasattr(logging, method_name):
        raise AttributeError(f"{method_name} already defined in logging module")
    if hasattr(logging.getLoggerClass(), method_name):
        raise AttributeError(f"{method_name} already defined in logger class")

    def log_for_level(self, message, *args, **kwargs):
        if self.isEnabledFor(level_num):
            self._log(level_num, message, args, **kwargs)

    def log_to_root(message, *args, **kwargs):
        logging.log(level_num, message, *args, **kwargs)

    logging.addLevelName(level_num, level_name)
    setattr(logging, level_name, level_num)
    setattr(logging.getLoggerClass(), method_name, log_for_level)
    setattr(logging, method_name, log_to_root)


add_logging_level("SUCCESS", logging.INFO + 5)


def supports_color() -> bool:
    """Check if the terminal supports ANSI color codes.

    Detects if the terminal supports ANSI color codes by checking platform-specific
    conditions and environment variables. On Windows, it also checks the Windows
    registry for the VirtualTerminalLevel key.

    Returns:
        bool: True if the terminal supports color, False otherwise
    """

    def vt_codes_enabled_in_windows_registry():
        try:
            import winreg
        except ImportError:
            return False

        try:
            reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Console")
            reg_key_value, _ = winreg.QueryValueEx(reg_key, "VirtualTerminalLevel")
            return reg_key_value == 1
        except FileNotFoundError:
            return False

    is_a_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    if not is_a_tty:
        return False

    if sys.platform == "win32":
        return (
            getattr(colorama, "fixed_windows_console", False)
            or "ANSICON" in os.environ
            or "WT_SESSION" in os.environ  # Windows Terminal
            or os.environ.get("TERM_PROGRAM") == "vscode"
            or vt_codes_enabled_in_windows_registry()
        )

    return True


if supports_color():
    try:
        if sys.platform == "win32":
            colorama.just_fix_windows_console()
        else:
            colorama.init()
    except (AttributeError, ImportError, OSError):
        HAS_COLOR_SUPPORT = False
    else:
        HAS_COLOR_SUPPORT = True
else:
    HAS_COLOR_SUPPORT = False


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
        "SUCCESS": Fore.LIGHTCYAN_EX,
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
                r"\$\$\'(.*?)\'\$\$",
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


def setup_logger(log_name: str, log_level: str, log_dir: str) -> logging.Logger:
    """Configures a logger with console and file output.

    Creates a logger that writes to both console (with colors) and a rotating
    log file (without colors). The log format varies based on log level.

    Args:
        log_name (str): Name of the logger and base name for log file
        log_level (str): Logging level ('DEBUG', 'INFO', 'SUCCESS', etc.)
        log_dir (str): Directory where log files will be stored

    Returns:
        logging.Logger: Configured logger instance
    """
    if log_level == "SUCCESS":
        log_level_literal = logging.SUCCESS
    else:
        log_level_literal = getattr(logging, log_level)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(log_name)
    logger.setLevel(log_level_literal)

    if not logger.handlers:
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
            if HAS_COLOR_SUPPORT
            else CleanFormatter(
                log_format,
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

        log_file = log_path / f"{log_name}.{log_level}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(log_level_literal)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(log_level_literal)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
