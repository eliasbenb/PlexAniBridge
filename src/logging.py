import logging
from datetime import datetime
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

    def format(self, record):
        orig_levelname = record.levelname
        record.levelname = f"{self.COLORS.get(record.levelname, '')}{record.levelname}{Style.RESET_ALL}"
        result = super().format(record)
        record.levelname = orig_levelname
        return result


def setup_logger(log_name: str, log_level: str, log_dir: str):
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

        file_formatter = logging.Formatter(
            log_format,
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_formatter = ColorFormatter(
            log_format,
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        log_file = (
            log_path
            / f'{log_name}.{"." if log_level_literal == logging.INFO else f"{log_level}."}{datetime.now().strftime("%Y%m%d")}.log'
        )
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
