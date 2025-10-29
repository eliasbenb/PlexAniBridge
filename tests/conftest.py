"""Shared pytest configuration for core tests."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="pab-tests-"))

os.environ.setdefault("PAB_DATA_PATH", str(_TEST_DATA_DIR))
os.environ.setdefault("PAB_ANILIST_TOKEN", "anilist-token")
os.environ.setdefault("PAB_PLEX_TOKEN", "plex-token")
os.environ.setdefault("PAB_PLEX_USER", "eliasbenb")
os.environ.setdefault("PAB_PLEX_URL", "http://plex:32400")


@atexit.register
def _cleanup_test_data_dir() -> None:
    """Remove the temporary test data directory after the test session."""
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
