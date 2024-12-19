import sys
from pathlib import Path

import tomlkit
from git import InvalidGitRepositoryError, Repo


def get_pyproject_version() -> str:
    """Get the PlexAniBridge's version from the pyproject.toml file

    Returns:
        str: PlexAniBridge's version
    """
    toml_file = Path(sys.argv[0]).parent / "pyproject.toml"

    if not toml_file.exists() or not toml_file.is_file():
        return "unknown"

    toml_data = tomlkit.load(toml_file.open())
    if "project" in toml_data and "version" in toml_data["project"]:
        return toml_data["project"]["version"]

    return "unknown"


def get_git_hash() -> str:
    """Get the git commit hash of the PlexAniBridge repository

    Returns:
        str: PlexAniBridge's current commit hash
    """
    try:
        repo = Repo(Path(sys.argv[0]), search_parent_directories=True)
        return repo.head.commit.hexsha
    except InvalidGitRepositoryError:
        return "unknown"
