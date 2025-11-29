"""Tests for settings configuration utilities."""

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


def test_profile_parent_requires_assignment() -> None:
    """Test that accessing parent on unassigned profile raises ProfileConfigError."""
    profile = AniBridgeProfileConfig(
        provider_config={
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
    config = AniBridgeConfig()
    # Default profile should be created implicitly and accessible
    profile = config.get_profile("default")
    assert profile is not None


def test_config_creates_default_profile_from_globals() -> None:
    """Test that AniBridgeConfig creates a default profile from global settings."""
    config = AniBridgeConfig(
        global_config=AniBridgeProfileConfig(
            provider_config={
                "anilist": {"token": "anilist-token"},
                "plex": {
                    "token": "plex-token",
                    "user": "eliasbenb",
                    "url": "http://plex:32400",
                    "sections": ["Anime"],
                },
            }
        )
    )

    profile = config.get_profile("default")

    assert profile.parent is config
    assert profile.provider_config["anilist"]["token"] == "anilist-token"
    assert profile.provider_config["plex"]["token"] == "plex-token"
    assert profile.provider_config["plex"]["user"] == "eliasbenb"
    assert profile.provider_config["plex"]["url"] == "http://plex:32400"
    assert profile.provider_config["plex"]["sections"] == ["Anime"]


def test_config_profile_inherits_global_values() -> None:
    """Test that a profile inherits global settings from AniBridgeConfig."""
    config = AniBridgeConfig(
        global_config=AniBridgeProfileConfig(
            provider_config={
                "plex": {"url": "http://global"},
            }
        ),
        profiles={
            "primary": AniBridgeProfileConfig(
                provider_config={
                    "anilist": {"token": "anilist-token"},
                }
            )
        },
    )

    profile = config.get_profile("primary")

    assert profile.provider_config["plex"]["url"] == "http://global"


def test_get_profile_raises_for_unknown_name(
    tmp_path: Path,
) -> None:
    """Test that get_profile raises ProfileNotFoundError for unknown profile names."""
    config = AniBridgeConfig()

    with pytest.raises(ProfileNotFoundError):
        config.get_profile("missing")
