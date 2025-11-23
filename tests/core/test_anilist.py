"""Tests for the AniList client."""

import pytest

from src.core.anilist import AniListClient
from src.exceptions import AniListFilterError
from src.models.schemas.anilist import Media, MediaFormat, MediaStatus


@pytest.mark.asyncio
async def test_search_media_ids_requires_filter() -> None:
    """Reject empty filters when searching for media IDs."""
    client = AniListClient(anilist_token=None)

    with pytest.raises(AniListFilterError):
        await client.search_media_ids(filters={})

    await _clear_search_media_ids_cache(client)


@pytest.mark.asyncio
async def test_search_media_ids_rejects_unknown_filter() -> None:
    """Reject unsupported filter arguments."""
    client = AniListClient(anilist_token=None)

    with pytest.raises(AniListFilterError):
        await client.search_media_ids(filters={"fake": 1})

    await _clear_search_media_ids_cache(client)


@pytest.mark.asyncio
async def test_search_media_ids_collects_unique_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collect unique identifiers across paged responses."""
    client = AniListClient(anilist_token=None)

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

    await _clear_search_media_ids_cache(client)


@pytest.mark.asyncio
async def test_batch_get_anime_combines_cached_and_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Combine cached entries with freshly fetched media in requested order."""
    client = AniListClient(anilist_token=None)

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


async def _clear_search_media_ids_cache(client: AniListClient) -> None:
    cache = getattr(client.search_media_ids, "cache", None)
    if cache is not None:
        await cache.clear()
