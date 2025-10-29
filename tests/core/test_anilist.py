"""Tests for the AniList client."""

from pathlib import Path

import pytest

from src.core.anilist import AniListClient
from src.exceptions import AniListFilterError


@pytest.mark.asyncio
async def test_search_media_ids_requires_filter(tmp_path: Path) -> None:
    """Reject empty filters when searching for media IDs."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )

    with pytest.raises(AniListFilterError):
        await client.search_media_ids(filters={})


@pytest.mark.asyncio
async def test_search_media_ids_rejects_unknown_filter(tmp_path: Path) -> None:
    """Reject unsupported filter arguments."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )

    with pytest.raises(AniListFilterError):
        await client.search_media_ids(filters={"fake": 1})


@pytest.mark.asyncio
async def test_search_media_ids_collects_unique_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Collect unique identifiers across paged responses."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )

    call_vars: list[dict] = []

    async def fake_make_request(
        self: AniListClient, query: str, variables: dict | None = None
    ):
        call_vars.append(variables or {})
        page = (variables or {}).get("page_1", 1)
        if page <= 1:
            return {
                "data": {
                    "batch1": {
                        "pageInfo": {"hasNextPage": True},
                        "media": [{"id": 1}, {"id": 2}],
                    }
                }
            }
        return {
            "data": {
                "batch1": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [{"id": 3}],
                }
            }
        }

    monkeypatch.setattr(
        AniListClient, "_make_request", fake_make_request, raising=False
    )

    result = await client.search_media_ids(
        filters={"search": "test"}, max_results=3, per_page=100
    )

    assert result == [1, 2, 3]
    assert call_vars and call_vars[0]["perPage"] == 50

    cache = getattr(client.search_media_ids, "cache", None)
    if cache is not None:
        await cache.clear()
