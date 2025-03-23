import locale
import sys


def supports_utf8():
    encoding = sys.stdout.encoding or locale.getpreferredencoding(False)
    return encoding.lower().startswith("utf")
