"""Tests for the core mappings client."""

import json
from pathlib import Path

import pytest

from src.core.mappings import MappingsClient


def _make_client(tmp_path: Path) -> MappingsClient:
    """Helper to create a MappingsClient for testing."""
    return MappingsClient(data_path=tmp_path, upstream_url=None)


def test_deep_merge_merges_nested_dicts_and_preserves_special_keys(
    tmp_path: Path,
) -> None:
    """Test that _deep_merge correctly merges nested dictionaries."""
    client = _make_client(tmp_path)

    left = {
        "100": {
            "anidb_id": 555,
            "tmdb_show_id": 111,
            "tmdb_mappings": {"s1": "e1-e12"},
        },
        "200": {"mal_id": [9876, 5432]},
    }
    right = {
        "100": {
            "mal_id": 321,
            "tmdb_mappings": {"s1": "e1-e24"},
        },
        "300": {"tmdb_movie_id": 999},
    }

    merged = client._deep_merge(left, right)

    assert merged["100"]["anidb_id"] == 555
    assert merged["100"]["mal_id"] == 321
    assert merged["100"]["tmdb_mappings"] == {"s1": "e1-e24"}
    assert merged["200"]["mal_id"] == [9876, 5432]
    assert merged["300"]["tmdb_movie_id"] == 999


def test_resolve_path_handles_relative_file_include(tmp_path: Path) -> None:
    """Test that _resolve_path correctly resolves relative file includes."""
    client = _make_client(tmp_path)

    parent_path = tmp_path / "parent.yaml"
    parent_path.write_text("{}", encoding="utf-8")

    child_dir = tmp_path / "includes"
    child_dir.mkdir()
    child_path = child_dir / "child.json"
    child_path.write_text("{}", encoding="utf-8")

    resolved = client._resolve_path("includes/child.json", str(parent_path))

    assert resolved == child_path.resolve().as_posix()


def test_resolve_path_handles_relative_url_include(tmp_path: Path) -> None:
    """Test that _resolve_path correctly resolves relative URL includes."""
    client = _make_client(tmp_path)

    resolved = client._resolve_path(
        "child.json", "https://example.com/mappings/root.yaml"
    )

    assert resolved == "https://example.com/mappings/child.json"


def test_dict_str_keys_normalizes_nested_structures(tmp_path: Path) -> None:
    """Test that _dict_str_keys converts all dict keys to strings recursively."""
    client = _make_client(tmp_path)

    data = {
        1: {"nested": {2: "value"}},
        "list": [{3: "v"}],
    }

    normalized = client._dict_str_keys(data)

    assert normalized == {
        "1": {"nested": {"2": "value"}},
        "list": [{"3": "v"}],
    }


@pytest.mark.asyncio
async def test_load_mappings_merges_custom_files_and_tracks_provenance(
    tmp_path: Path,
) -> None:
    """Test that load_mappings merges included files and tracks provenance."""
    data_path = tmp_path / "data"
    data_path.mkdir()

    parent_path = data_path / "mappings.custom.yaml"
    child_path = data_path / "child.json"

    parent_path.write_text(
        """
$includes:
  - child.json
1:
    mal_id: 555
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    child_path.write_text(
        json.dumps(
            {
                "1": {
                    "tmdb_show_id": 101,
                    "tmdb_mappings": {"s1": "e1-e12"},
                },
                "2": {"tmdb_movie_id": 202},
            }
        ),
        encoding="utf-8",
    )

    client = MappingsClient(data_path=data_path, upstream_url=None)

    try:
        result = await client.load_mappings()
    finally:
        await client.close()

    assert "1" in result
    assert result["1"]["mal_id"] == 555
    assert result["1"]["tmdb_show_id"] == 101
    assert result["1"]["tmdb_mappings"] == {"s1": "e1-e12"}
    assert "2" in result
    assert "$includes" not in result

    provenance = client.get_provenance()

    child_resolved = str(child_path.resolve())
    parent_resolved = str(parent_path.resolve())

    assert provenance[1] == [child_resolved, parent_resolved]
    assert provenance[2] == [child_resolved, parent_resolved]


@pytest.mark.asyncio
async def test_load_mappings_prefers_custom_over_upstream(tmp_path: Path) -> None:
    """Custom mappings override upstream values while keeping nested data."""
    data_path = tmp_path / "data"
    data_path.mkdir()

    upstream_path = data_path / "upstream.json"
    upstream_path.write_text(
        json.dumps(
            {
                "1": {
                    "tmdb_show_id": 111,
                    "tmdb_mappings": {"s1": "e1-e12"},
                }
            }
        ),
        encoding="utf-8",
    )

    custom_path = data_path / "mappings.custom.json"
    custom_path.write_text(
        json.dumps(
            {
                "1": {"tmdb_show_id": 222},
                "2": {"tmdb_movie_id": 303},
            }
        ),
        encoding="utf-8",
    )

    client = MappingsClient(data_path=data_path, upstream_url=str(upstream_path))

    try:
        result = await client.load_mappings()
    finally:
        await client.close()

    assert result["1"]["tmdb_show_id"] == 222
    assert result["1"]["tmdb_mappings"] == {"s1": "e1-e12"}
    assert result["2"]["tmdb_movie_id"] == 303


@pytest.mark.asyncio
async def test_load_mappings_uses_first_existing_custom_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Only the first existing mappings file is used when multiple are present."""
    caplog.set_level("WARNING", logger="PlexAniBridge")

    data_path = tmp_path / "data"
    data_path.mkdir()

    (data_path / "mappings.custom.yaml").write_text(
        """
1:
  tmdb_show_id: 101
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    (data_path / "mappings.custom.json").write_text(
        json.dumps({"1": {"tmdb_show_id": 202}}),
        encoding="utf-8",
    )

    client = MappingsClient(data_path=data_path, upstream_url=None)

    try:
        result = await client.load_mappings()
    finally:
        await client.close()

    assert result["1"]["tmdb_show_id"] == 101
    assert any(
        "Found multiple custom mappings files" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_load_mappings_handles_circular_includes(tmp_path: Path) -> None:
    """Circular includes are skipped while preserving merged data."""
    data_path = tmp_path / "data"
    data_path.mkdir()

    (data_path / "a.json").write_text(
        json.dumps(
            {
                "$includes": ["b.json"],
                "1": {"tmdb_show_id": 101},
            }
        ),
        encoding="utf-8",
    )

    (data_path / "b.json").write_text(
        json.dumps(
            {
                "$includes": ["a.json"],
                "1": {"tmdb_mappings": {"s1": "e1-e12"}},
                "2": {"tmdb_movie_id": 202},
            }
        ),
        encoding="utf-8",
    )

    (data_path / "mappings.custom.json").write_text(
        json.dumps(
            {
                "$includes": ["a.json"],
                "1": {"tmdb_show_id": 999},
                "3": {"tmdb_show_id": 303},
            }
        ),
        encoding="utf-8",
    )

    client = MappingsClient(data_path=data_path, upstream_url=None)

    try:
        result = await client.load_mappings()
    finally:
        await client.close()

    assert result["1"]["tmdb_show_id"] == 999
    assert result["1"]["tmdb_mappings"] == {"s1": "e1-e12"}
    assert result["2"]["tmdb_movie_id"] == 202
    assert result["3"]["tmdb_show_id"] == 303

    provenance = client.get_provenance()
    assert provenance[1] == [
        str((data_path / "b.json").resolve()),
        str((data_path / "a.json").resolve()),
        str((data_path / "mappings.custom.json").resolve()),
    ]


@pytest.mark.asyncio
async def test_get_provenance_skips_non_int_keys(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Non-numeric keys are excluded from the provenance output."""
    caplog.set_level("WARNING", logger="PlexAniBridge")

    data_path = tmp_path / "data"
    data_path.mkdir()

    (data_path / "mappings.custom.json").write_text(
        json.dumps(
            {
                "123": {"tmdb_show_id": 777},
                "abc": {"tmdb_movie_id": 888},
            }
        ),
        encoding="utf-8",
    )

    client = MappingsClient(data_path=data_path, upstream_url=None)

    try:
        await client.load_mappings()
    finally:
        await client.close()

    provenance = client.get_provenance()
    assert list(provenance.keys()) == [123]
    assert any(
        "Skipping invalid anilist_id" in record.message for record in caplog.records
    )
