"""Tests for settings configuration utilities."""

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from src.config.settings import (
    AniBridgeConfig,
    AniBridgeProfileConfig,
    find_yaml_config_file,
)
from src.exceptions import (
    ProfileConfigError,
    ProfileNotFoundError,
)


@pytest.fixture(autouse=True)
def clear_ab_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear AniBridge-related environment variables before each test."""
    for key in list(os.environ):
        if key.startswith("AB_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def isolate_working_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Set the working directory to a temporary path for each test."""
    monkeypatch.chdir(tmp_path)


def test_find_yaml_config_file_prefers_data_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that find_yaml_config_file prefers AB_DATA_PATH environment variable."""
    monkeypatch.setenv("AB_DATA_PATH", str(tmp_path))
    config_file = tmp_path / "config.yaml"
    config_file.write_text("root: true", encoding="utf-8")

    result = find_yaml_config_file()

    assert result == config_file.resolve()


def test_find_yaml_config_file_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that find_yaml_config_file falls back to current working directory."""
    monkeypatch.delenv("AB_DATA_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "config.yml"
    config_file.write_text("foo: bar", encoding="utf-8")

    result = find_yaml_config_file()

    assert result == config_file.resolve()


def test_profile_parent_requires_assignment() -> None:
    """Test that accessing parent on unassigned profile raises ProfileConfigError."""
    profile = AniBridgeProfileConfig(
        providers={
            "anilist": {"token": SecretStr("anilist-token")},
            "plex": {
                "token": SecretStr("plex-token"),
                "user": "eliasbenb",
                "url": "http://plex:32400",
            },
        }
    )

    with pytest.raises(ProfileConfigError):
        _ = profile.parent


def test_config_requires_profile_or_globals(tmp_path: Path) -> None:
    """Test AniBridgeConfig bootstraps a default profile when no explicit provider.

    configs are provided.
    """
    config = AniBridgeConfig(data_path=tmp_path)
    # Default profile should be created implicitly and accessible
    profile = config.get_profile("default")
    assert profile is not None


def test_config_creates_default_profile_from_globals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that AniBridgeConfig creates a default profile from global settings."""
    monkeypatch.setenv("AB_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("AB_PROVIDERS__ANILIST__TOKEN", "anilist-token")
    monkeypatch.setenv("AB_PROVIDERS__PLEX__TOKEN", "plex-token")
    monkeypatch.setenv("AB_PROVIDERS__PLEX__USER", "eliasbenb")
    monkeypatch.setenv("AB_PROVIDERS__PLEX__URL", "http://plex:32400")
    monkeypatch.setenv("AB_PROVIDERS__PLEX__SECTIONS", '["Anime"]')

    config = AniBridgeConfig()

    profile = config.get_profile("default")

    assert profile.parent is config
    assert profile.providers["anilist"]["token"] == "anilist-token"
    assert profile.providers["plex"]["token"] == "plex-token"
    assert profile.providers["plex"]["user"] == "eliasbenb"
    assert profile.providers["plex"]["url"] == "http://plex:32400"
    assert profile.providers["plex"]["sections"] == ["Anime"]


def test_config_profile_inherits_global_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a profile inherits global settings from AniBridgeConfig."""
    monkeypatch.setenv("AB_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("AB_PROVIDERS__PLEX__URL", "http://global")
    monkeypatch.setenv(
        "AB_PROFILES__primary__PROVIDERS__ANILIST__TOKEN", "anilist-token"
    )
    monkeypatch.setenv("AB_PROFILES__primary__PROVIDERS__PLEX__TOKEN", "plex-token")
    monkeypatch.setenv("AB_PROFILES__primary__PROVIDERS__PLEX__USER", "eliasbenb")

    config = AniBridgeConfig()

    profile = config.get_profile("primary")

    assert profile.providers["plex"]["url"] == "http://global"


def test_get_profile_raises_for_unknown_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that get_profile raises ProfileNotFoundError for unknown profile names."""
    monkeypatch.setenv("AB_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("AB_ANILIST_TOKEN", "anilist-token")
    monkeypatch.setenv("AB_PLEX_TOKEN", "plex-token")
    monkeypatch.setenv("AB_PLEX_USER", "eliasbenb")
    monkeypatch.setenv("AB_PLEX_URL", "http://plex:32400")

    config = AniBridgeConfig()

    with pytest.raises(ProfileNotFoundError):
        config.get_profile("missing")
