import locale
import sys


def supports_utf8() -> bool:
    """Check if the terminal supports UTF-8 encoding.

    Returns:
        bool: True if the terminal supports UTF-8 encoding, False otherwise
    """
    encoding = sys.stdout.encoding or locale.getpreferredencoding(False)
    return encoding.lower().startswith("utf")
