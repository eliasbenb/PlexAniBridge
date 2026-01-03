"""Tests for the core mappings client (descriptor graph)."""

import json
from pathlib import Path

import pytest

from src.core.mappings import MappingsClient


def _make_client(tmp_path: Path) -> MappingsClient:
    return MappingsClient(data_path=tmp_path, upstream_url=None)


def test_deep_merge_merges_descriptor_targets(tmp_path: Path) -> None:
    """Deep merging of mappings combines descriptor targets correctly."""
    client = _make_client(tmp_path)
    left = {
        "anilist:1:movie": {
            "tmdb:10:movie": {"1": None},
        }
    }
    right = {
        "anilist:1:movie": {
            "tvdb:20:movie": {"1": "1-12"},
        },
        "tmdb:2:movie": {"anilist:3:movie": {"1": None}},
    }

    merged = client._deep_merge(left, right)

    assert merged["anilist:1:movie"]["tmdb:10:movie"] == {"1": None}
    assert merged["anilist:1:movie"]["tvdb:20:movie"] == {"1": "1-12"}
    assert merged["tmdb:2:movie"] == {"anilist:3:movie": {"1": None}}


def test_resolve_path_handles_relative_paths_and_urls(tmp_path: Path) -> None:
    """Resolving relative paths and URLs works correctly."""
    client = _make_client(tmp_path)
    parent_path = tmp_path / "parent.yaml"
    parent_path.write_text("{}", encoding="utf-8")

    child_dir = tmp_path / "includes"
    child_dir.mkdir()
    child_path = child_dir / "child.json"
    child_path.write_text("{}", encoding="utf-8")

    resolved_file = client._resolve_path("includes/child.json", str(parent_path))
    resolved_url = client._resolve_path(
        "child.json", "https://example.com/mappings/root.yaml"
    )

    assert resolved_file == child_path.resolve().as_posix()
    assert resolved_url == "https://example.com/mappings/child.json"


def test_dict_str_keys_normalizes_nested_structures(tmp_path: Path) -> None:
    """Normalizing dictionary keys to strings works for nested structures."""
    client = _make_client(tmp_path)
    data = {1: {"nested": {2: "value"}}, "list": [{3: "v"}]}
    normalized = client._dict_str_keys(data)
    assert normalized == {
        "1": {"nested": {"2": "value"}},
        "list": [{"3": "v"}],
    }


@pytest.mark.asyncio
async def test_get_provenance_preserves_descriptor_keys(tmp_path: Path) -> None:
    """Getting provenance preserves the original descriptor keys."""
    data_path = tmp_path / "data"
    data_path.mkdir()

    custom_path = data_path / "mappings.json"
    custom_path.write_text(
        json.dumps(
            {
                "123": {"tmdb:1:movie": {"1": None}},
                "abc:def:movie": {"tmdb:2:movie": {"1": None}},
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
    assert set(provenance.keys()) == {"123", "abc:def:movie"}
