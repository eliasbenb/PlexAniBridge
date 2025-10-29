"""Tests for logging utilities."""

import logging

import colorama

from src.utils.logging import CleanFormatter, ColorFormatter, Logger


def test_color_formatter_applies_color_codes():
    """Test that ColorFormatter applies color codes to marked sections."""
    formatter = ColorFormatter("%(levelname)s:%(message)s")
    original_message = "$$'value'$$ $${key: value}$$ message"
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg=original_message,
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert colorama.Fore.GREEN in formatted
    assert colorama.Fore.LIGHTBLUE_EX in formatted
    assert colorama.Style.DIM in formatted
    assert record.msg == original_message


def test_clean_formatter_removes_markers():
    """Test that CleanFormatter removes special markers from the message."""
    formatter = CleanFormatter("%(message)s")
    original_message = "wrapped $$'value'$$ and $${key: 1}$$"
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg=original_message,
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert "$$" not in formatted
    assert "'value'" in formatted
    assert "{key: 1}" in formatted
    assert record.msg == original_message


def test_logger_prefixes_class_name():
    """Test that Logger prefixes messages with the class name."""
    logger = Logger("test")
    logger.setLevel(logging.DEBUG)
    captured = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    logger.addHandler(ListHandler())

    class Sample:
        def __init__(self, bound_logger: Logger):
            self.log = bound_logger

        def run(self):
            self.log.info("hello")

    Sample(logger).run()

    assert captured and captured[0] == "Sample: hello"


def test_logger_success_level_records_message():
    """Test that Logger logs messages at SUCCESS level."""
    logger = Logger("test")
    logger.setLevel(Logger.SUCCESS)
    records: list[logging.LogRecord] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger.addHandler(CaptureHandler())

    logger.success("operation complete")

    assert records, "Expected at least one log record"
    record = records[0]
    assert record.levelno == Logger.SUCCESS
    assert record.levelname == "SUCCESS"
    assert record.getMessage() == "operation complete"
