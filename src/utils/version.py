import sys
from pathlib import Path

import tomlkit


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
        git_dir_path = Path(sys.argv[0]).parent / ".git"
        if not git_dir_path.exists() or not git_dir_path.is_dir():
            return "unknown"

        with open(git_dir_path / "HEAD") as f:
            ref = f.read().strip().split(": ")[1]

        if ref.startswith("refs/heads/"):
            ref = ref[11:]
        else:
            return "unknown"

        ref_path = git_dir_path / "refs" / "heads" / ref
        if not ref_path.exists() or not ref_path.is_file():
            return "unknown"

        with open(ref_path) as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def get_docker_status() -> bool:
    """Check if PlexAniBridge is running inside a Docker container"

    Returns:
        bool: True if running inside a Docker container, False otherwise
    """
    dockerenv_path = Path("/.dockerenv")
    return dockerenv_path.exists() and dockerenv_path.is_file()
