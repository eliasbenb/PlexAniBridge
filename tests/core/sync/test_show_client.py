"""Unit tests for `src.core.sync.show`."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest
from anibridge.library import (
    LibraryEpisode as LibraryEpisodeProtocol,
)
from anibridge.library import (
    LibrarySeason as LibrarySeasonProtocol,
)
from anibridge.library import (
    LibraryShow as LibraryShowProtocol,
)
from anibridge.list import ListEntry as ListEntryProtocol
from anibridge.list import ListMediaType, ListStatus

from src.core.animap import AnimapDescriptor, AnimapEdge, AnimapGraph
from src.core.sync.show import ShowSyncClient
from src.models.db.sync_history import SyncHistory
from tests.core.sync.fakes import (
    FakeAnimapClient,
    FakeLibraryEpisode,
    FakeLibraryProvider,
    FakeLibrarySeason,
    FakeLibraryShow,
    FakeListEntry,
    FakeListProvider,
    make_history_entry,
)

if TYPE_CHECKING:
    from src.config.database import AniBridgeDB


@pytest.fixture
def show_client() -> ShowSyncClient:
    """Provide a configured show sync client."""
    return ShowSyncClient(
        library_provider=cast(Any, FakeLibraryProvider()),
        list_provider=cast(Any, FakeListProvider()),
        animap_client=cast(Any, FakeAnimapClient()),
        excluded_sync_fields=[],
        full_scan=False,
        destructive_sync=False,
        search_fallback_threshold=80,
        batch_requests=False,
        dry_run=False,
        profile_name="tester",
    )


def build_show(
    *,
    view_counts: Sequence[int],
    ordering: str = "tvdb",
    show_kwargs: dict[str, Any] | None = None,
    season_kwargs: dict[str, Any] | None = None,
    episode_kwargs: dict[str, Any] | None = None,
) -> tuple[FakeLibraryShow, FakeLibrarySeason, list[FakeLibraryEpisode]]:
    """Construct a fake show with a single season and configurable episodes."""
    show = FakeLibraryShow(
        key="show-1",
        title="Show",
        ordering=ordering,
        **(show_kwargs or {}),
    )
    season = FakeLibrarySeason(
        key="season-1",
        title="S1",
        index=1,
        show=show,
        **(season_kwargs or {}),
    )
    episodes: list[FakeLibraryEpisode] = []
    for idx, count in enumerate(view_counts, start=1):
        episodes.append(
            FakeLibraryEpisode(
                key=f"ep-{idx}",
                title=f"Episode {idx}",
                index=idx,
                season_index=1,
                show=show,
                season=season,
                view_count=count,
                **(episode_kwargs or {}),
            )
        )
    season._episodes = list(episodes)
    show.attach_children(episodes=episodes, seasons=[season])
    return show, season, episodes


def make_graph(
    source: tuple[str, str, str],
    target: tuple[str, str, str],
    source_range: str = "s1",
    destination_range: str | None = None,
) -> AnimapGraph:
    """Helper to build a one-edge mapping graph for show tests."""
    edge = AnimapEdge(
        source=AnimapDescriptor(*source),
        destination=AnimapDescriptor(*target),
        source_range=source_range,
        destination_range=destination_range,
    )
    return AnimapGraph(edges=(edge,))


@pytest.mark.asyncio
async def test_process_media_syncs_show_and_writes_history(
    show_client: ShowSyncClient, sync_db: AniBridgeDB
) -> None:
    """Processing a show syncs its episodes and writes history entries."""
    provider = cast(FakeListProvider, show_client.list_provider)
    show, _, episodes = build_show(view_counts=[2, 2])
    entry = FakeListEntry(
        provider=provider,
        key="400",
        title="Show",
        media_type=ListMediaType.TV,
        total_units=len(episodes),
    )
    provider.entries["400"] = entry
    provider.resolved_key = "400"
    show_client.animap_client = cast(
        Any,
        FakeAnimapClient(
            make_graph(
                ("anilist", "400", "s1"),
                ("tmdb", "900", "s1"),
            )
        ),
    )

    await show_client.process_media(cast(LibraryShowProtocol, show))

    assert provider.updated_entries and provider.updated_entries[0][0] == "400"
    assert show_client.sync_stats.synced >= 1
    with sync_db as ctx:
        assert ctx.session.query(SyncHistory).count() == 1


@pytest.mark.asyncio
async def test_map_media_uses_mapping_resolution(show_client: ShowSyncClient) -> None:
    """Mapping graphs resolve to list entries when provider supports it."""
    provider = cast(FakeListProvider, show_client.list_provider)
    show, season, episodes = build_show(view_counts=[1, 1])
    entry = FakeListEntry(
        provider=provider,
        key="401",
        title="Show",
        media_type=ListMediaType.TV,
        total_units=len(episodes),
    )
    provider.entries["401"] = entry
    provider.resolved_key = "401"
    show_client.animap_client = cast(
        Any,
        FakeAnimapClient(
            make_graph(
                ("tmdb", "10", "s1"),
                ("anilist", "401", "s1"),
                source_range="s1",
            )
        ),
    )

    results = [
        result
        async for result in show_client.map_media(cast(LibraryShowProtocol, show))
    ]

    assert len(results) == 1
    mapped_season, mapped_eps, mapping, mapped_entry, media_key = results[0]
    assert mapped_season is season
    assert list(mapped_eps) == episodes
    assert mapping is not None
    assert mapped_entry is entry
    assert media_key == "401"


@pytest.mark.asyncio
async def test_search_media_prefers_matching_unit_counts(
    show_client: ShowSyncClient,
) -> None:
    """Ensure search results prefer entries with matching episode counts."""
    provider = cast(FakeListProvider, show_client.list_provider)
    show, season, episodes = build_show(view_counts=[0, 0])
    provider.search_results = [
        FakeListEntry(
            provider=provider,
            key="500",
            title="Show",
            media_type=ListMediaType.TV,
            total_units=len(episodes),
        ),
        FakeListEntry(
            provider=provider,
            key="501",
            title="Show Variant",
            media_type=ListMediaType.TV,
            total_units=len(episodes) + 2,
        ),
    ]
    show_client.search_fallback_threshold = 0

    entry = await show_client.search_media(
        cast(LibraryShowProtocol, show),
        cast(LibrarySeasonProtocol, season),
    )

    assert entry is provider.search_results[0]


@pytest.mark.asyncio
async def test_calculate_status_variants(show_client: ShowSyncClient) -> None:
    """Exercise the status calculator across watch states."""
    show, season, episodes = build_show(
        view_counts=[2, 2],
        show_kwargs={"on_watching": True},
        episode_kwargs={"on_watching": True},
    )
    entry = FakeListEntry(
        provider=FakeListProvider(),
        key="entry",
        title="Show",
        media_type=ListMediaType.TV,
        total_units=len(episodes),
    )
    status = await show_client._calculate_status(
        item=cast(LibraryShowProtocol, show),
        child_item=cast(LibrarySeasonProtocol, season),
        grandchild_items=cast(Sequence[LibraryEpisodeProtocol], tuple(episodes)),
        entry=cast(ListEntryProtocol, entry),
        mapping=None,
    )
    assert status == ListStatus.REPEATING

    entry.total_units = 10
    status = await show_client._calculate_status(
        item=cast(LibraryShowProtocol, show),
        child_item=cast(LibrarySeasonProtocol, season),
        grandchild_items=cast(Sequence[LibraryEpisodeProtocol], tuple(episodes)),
        entry=cast(ListEntryProtocol, entry),
        mapping=None,
    )
    assert status == ListStatus.CURRENT

    planning_show, planning_season, planning_eps = build_show(
        view_counts=[0],
        show_kwargs={"on_watchlist": True},
        season_kwargs={"on_watchlist": True},
    )
    entry.total_units = 1
    status = await show_client._calculate_status(
        item=cast(LibraryShowProtocol, planning_show),
        child_item=cast(LibrarySeasonProtocol, planning_season),
        grandchild_items=cast(Sequence[LibraryEpisodeProtocol], tuple(planning_eps)),
        entry=cast(ListEntryProtocol, entry),
        mapping=None,
    )
    assert status == ListStatus.PLANNING


@pytest.mark.asyncio
async def test_calculate_review_prefers_episode_for_singletons(
    show_client: ShowSyncClient,
) -> None:
    """Prioritize specific episode reviews when only one episode exists."""
    episode_review = "Episode note"
    show, season, episodes = build_show(
        view_counts=[1], episode_kwargs={"review": episode_review}
    )
    entry = FakeListEntry(
        provider=FakeListProvider(),
        key="entry",
        title="Show",
        media_type=ListMediaType.TV,
        total_units=1,
    )

    review = await show_client._calculate_review(
        item=cast(LibraryShowProtocol, show),
        child_item=cast(LibrarySeasonProtocol, season),
        grandchild_items=cast(Sequence[LibraryEpisodeProtocol], tuple(episodes)),
        entry=cast(ListEntryProtocol, entry),
        mapping=None,
    )

    assert review == episode_review


@pytest.mark.asyncio
async def test_filter_history_by_episodes_sorts_records(
    show_client: ShowSyncClient,
) -> None:
    """Filter and order history entries to match watched episodes."""
    history = [
        make_history_entry("ep-1", ts=datetime(2025, 1, 5, tzinfo=UTC)),
        make_history_entry("ep-2", ts=datetime(2025, 1, 3, tzinfo=UTC)),
        make_history_entry("ignored", ts=datetime(2025, 1, 1, tzinfo=UTC)),
    ]
    show, _, episodes = build_show(
        view_counts=[1, 1],
        show_kwargs={"history": history},
    )

    filtered = await show_client._filter_history_by_episodes(
        cast(LibraryShowProtocol, show),
        cast(Sequence[LibraryEpisodeProtocol], tuple(episodes)),
    )

    assert [record.library_key for record in filtered] == ["ep-2", "ep-1"]
