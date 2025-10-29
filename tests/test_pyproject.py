"""Basic pytest smoke tests for PlexAniBridge."""

import re
import tomllib
from pathlib import Path

SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[+-][0-9A-Za-z-.]+)?$")


def test_project_metadata() -> None:
    """Ensure core project metadata is present and well-formed."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml should exist at the project root"

    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)

    project = pyproject.get("project")
    assert isinstance(project, dict), "[project] table must exist in pyproject.toml"

    assert project.get("name") == "PlexAniBridge"

    version = project.get("version")
    assert isinstance(version, str) and SEMVER_PATTERN.fullmatch(version), (
        "Version must follow semantic versioning"
    )
