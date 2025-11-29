"""Shared pytest configuration and fixtures for the test suite."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="ab-tests-"))
os.environ["AB_DATA_PATH"] = str(_TEST_DATA_DIR)
_TEST_CONFIG_FILE = _TEST_DATA_DIR / "config.yaml"

_TEST_CONFIG_FILE.write_text(
    yaml.safe_dump(
        {
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

from src.config import settings as settings_module  # noqa: E402
from src.web.state import get_app_state  # noqa: E402

settings_module.get_config.cache_clear()


@pytest.fixture(autouse=True)
def _reset_app_state():
    """Ensure each test interacts with a fresh AppState instance."""
    get_app_state.cache_clear()
    state = get_app_state()
    yield state
    get_app_state.cache_clear()


@atexit.register
def _cleanup_test_data_dir() -> None:
    """Remove the temporary test data directory after the test session."""
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
