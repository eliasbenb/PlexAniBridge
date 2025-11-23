"""Tests for the AniList client."""

from datetime import UTC, timedelta, timezone
from pathlib import Path

import pytest

from src.core.anilist import AniListClient
from src.exceptions import AniListFilterError
from src.models.schemas.anilist import (
    Media,
    MediaFormat,
    MediaStatus,
    User,
    UserOptions,
)


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


@pytest.mark.asyncio
async def test_search_anime_filters_releasing_and_episode_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Filter search results by release status and episode count."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )

    media_results = [
        Media(id=1, status=MediaStatus.RELEASING, episodes=10, format=MediaFormat.TV),
        Media(id=2, status=MediaStatus.FINISHED, episodes=24, format=MediaFormat.MOVIE),
        Media(id=3, status=MediaStatus.FINISHED, episodes=12, format=MediaFormat.TV),
    ]

    async def fake_search(
        self: AniListClient, search_str: str, is_movie: bool | None, limit: int = 10
    ) -> list[Media]:
        assert search_str == "foo"
        assert is_movie is False
        assert limit == 5
        return media_results

    monkeypatch.setattr(AniListClient, "_search_anime", fake_search, raising=False)

    results = [
        media
        async for media in client.search_anime(
            "foo", is_movie=False, episodes=24, limit=5
        )
    ]

    assert [m.id for m in results] == [1, 2]


@pytest.mark.asyncio
async def test_get_anime_returns_cached_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Return cached media without issuing a network request."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )
    cached_media = Media(
        id=42,
        status=MediaStatus.RELEASING,
        episodes=12,
        format=MediaFormat.TV,
    )
    client.offline_anilist_entries[42] = cached_media

    async def fail_request(self: AniListClient, query: str, variables=None):
        raise AssertionError("Network should not be called when cache is populated")

    monkeypatch.setattr(AniListClient, "_make_request", fail_request, raising=False)

    media = await client.get_anime(42)

    assert media is cached_media


@pytest.mark.asyncio
async def test_get_anime_fetches_and_caches_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fetch media from AniList when missing locally and cache the result."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )

    call_args: dict[str, dict] = {}

    async def fake_request(
        self: AniListClient, query: str, variables: dict | None = None
    ) -> dict:
        call_args["variables"] = variables or {}
        return {
            "data": {
                "Media": {
                    "id": 128,
                    "status": MediaStatus.FINISHED,
                    "format": MediaFormat.TV,
                }
            }
        }

    monkeypatch.setattr(AniListClient, "_make_request", fake_request, raising=False)

    media = await client.get_anime(128)

    assert call_args["variables"] == {"id": 128}
    assert media.id == 128
    assert client.offline_anilist_entries[128].id == 128


@pytest.mark.asyncio
async def test_batch_get_anime_combines_cached_and_remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Combine cached entries with freshly fetched media in requested order."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )

    cached_media = Media(id=1, status=MediaStatus.FINISHED, format=MediaFormat.TV)
    client.offline_anilist_entries[1] = cached_media

    request_ids: list[list[int]] = []

    async def fake_request(
        self: AniListClient, query: str, variables: dict | None = None
    ) -> dict:
        request_ids.append(list((variables or {}).get("ids", [])))
        return {
            "data": {
                "Page": {
                    "media": [
                        {
                            "id": 2,
                            "status": MediaStatus.FINISHED,
                            "format": MediaFormat.MOVIE,
                        },
                        {
                            "id": 3,
                            "status": MediaStatus.RELEASING,
                            "format": MediaFormat.ONA,
                        },
                    ]
                }
            }
        }

    monkeypatch.setattr(AniListClient, "_make_request", fake_request, raising=False)

    media = await client.batch_get_anime([1, 2, 3])

    assert request_ids == [[2, 3]]
    assert [m.id for m in media] == [1, 2, 3]
    assert set(client.offline_anilist_entries) == {1, 2, 3}


def test_get_user_tz_parses_timezone_offset(tmp_path: Path) -> None:
    """Parse user timezone offsets from AniList user options."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )

    client.user = User(
        id=1,
        name="tester",
        options=UserOptions(timezone="-05:30"),
    )
    tz = client.get_user_tz()
    assert tz == timezone(timedelta(hours=-5, minutes=-30))

    client.user = User(
        id=1,
        name="tester",
        options=UserOptions(timezone="+02:00"),
    )
    tz = client.get_user_tz()
    assert tz == timezone(timedelta(hours=2))


def test_get_user_tz_defaults_to_utc(tmp_path: Path) -> None:
    """Return UTC when timezone information is missing or invalid."""
    client = AniListClient(
        anilist_token=None,
        backup_dir=tmp_path,
        dry_run=False,
        profile_name="test",
    )
    client.user = User(id=1, name="tester", options=UserOptions(timezone="invalid"))

    tz = client.get_user_tz()

    assert tz == UTC
