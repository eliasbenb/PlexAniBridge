"""Shared pytest configuration for core tests."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="ab-tests-"))

os.environ.setdefault("AB_DATA_PATH", str(_TEST_DATA_DIR))
os.environ.setdefault("AB_ANILIST_TOKEN", "anilist-token")
os.environ.setdefault("AB_PLEX_TOKEN", "plex-token")
os.environ.setdefault("AB_PLEX_USER", "eliasbenb")
os.environ.setdefault("AB_PLEX_URL", "http://plex:32400")


@atexit.register
def _cleanup_test_data_dir() -> None:
    """Remove the temporary test data directory after the test session."""
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
