"""Shared pytest configuration for core tests."""

import atexit
import shutil
import tempfile
from pathlib import Path

import yaml

from src.config import settings as settings_module

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="ab-tests-"))
_TEST_CONFIG_FILE = _TEST_DATA_DIR / "config.yaml"

_TEST_CONFIG_FILE.write_text(
    yaml.safe_dump(
        {
            "data_path": str(_TEST_DATA_DIR),
            "providers": {
                "anilist": {"token": "anilist-token"},
                "plex": {
                    "token": "plex-token",
                    "user": "eliasbenb",
                    "url": "http://plex:32400",
                },
            },
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)

settings_module.get_config.cache_clear()


@atexit.register
def _cleanup_test_data_dir() -> None:
    """Remove the temporary test data directory after the test session."""
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
