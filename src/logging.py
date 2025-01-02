import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorama
from colorama import Fore, Style

colorama.init()


class ColorFormatter(logging.Formatter):
    """Custom formatter to add colors to console output"""

    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors

        Args:
            record (logging.LogRecord): The log record to format
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
    """Formatter that removes color markers from log messages"""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record without color markers

        Args:
            record (logging.LogRecord): The log record to format
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
    """Setup a logger with a file and console handler

    Args:
        log_name (str): The name of the logger
        log_level (str): The logging level
        log_dir (str): The directory to store the log files

    Returns:
        logging.Logger: The configured logger
    """
    log_level_literal = getattr(logging, log_level)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(log_name)
    logger.setLevel(log_level_literal)

    if not logger.handlers:
        log_format = (
            "%(asctime)s - %(name)s - %(levelname)s\t%(filename)s:%(lineno)d\t%(message)s"
            if log_level_literal == logging.DEBUG
            else "%(asctime)s - %(name)s - %(levelname)s\t%(message)s"
        )

        file_formatter = CleanFormatter(
            log_format,
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_formatter = ColorFormatter(
            log_format,
            datefmt="%Y-%m-%d %H:%M:%S",
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
