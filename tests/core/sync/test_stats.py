"""Unit tests for ``src.core.sync.stats`` components."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anibridge.library import LibraryEpisode as LibraryEpisodeProtocol
from anibridge.list import (
    ListEntry as ListEntryProtocol,
)
from anibridge.list import (
    ListMediaType,
    ListStatus,
)

from src.core.sync.stats import EntrySnapshot, ItemIdentifier, SyncOutcome, SyncStats
from src.exceptions import UnsupportedMediaTypeError
from tests.core.sync.fakes import (
    FakeLibraryEpisode,
    FakeLibrarySeason,
    FakeLibraryShow,
    FakeListEntry,
    FakeListProvider,
)


@pytest.fixture
def list_entry() -> ListEntryProtocol:
    """Provide a populated fake list entry for snapshot tests."""
    provider = FakeListProvider()
    entry = FakeListEntry(
        provider=provider,
        key="42",
        title="Test Show",
        media_type=ListMediaType.TV,
        total_units=12,
    )
    entry.status = ListStatus.CURRENT
    entry.progress = 6
    entry.repeats = 1
    entry.review = "So far so good"
    entry.user_rating = 80
    entry.started_at = datetime(2025, 1, 1, tzinfo=UTC)
    entry.finished_at = None
    return cast(ListEntryProtocol, entry)


def test_item_identifier_from_episode_includes_parent_metadata() -> None:
    """Episode identifiers include parent/season metadata for history tracking."""
    show = FakeLibraryShow(key="show-1", title="Show", ordering="tvdb")
    season = FakeLibrarySeason(key="season-1", title="S1", index=1, show=show)
    episode = FakeLibraryEpisode(
        key="ep-1",
        title="Episode 1",
        index=1,
        season_index=1,
        show=show,
        season=season,
    )
    show.attach_children(episodes=[episode], seasons=[season])

    identifier = ItemIdentifier.from_item(cast(LibraryEpisodeProtocol, episode))

    assert identifier.rating_key == "ep-1"
    assert identifier.parent_title == "Show"
    assert identifier.season_index == 1
    assert identifier.episode_index == 1
    assert identifier.item_type == "episode"


def test_item_identifier_from_season_includes_parent_metadata() -> None:
    """Season identifiers capture parent show context when available."""
    show = FakeLibraryShow(key="show-1", title="Show")
    season = FakeLibrarySeason(key="season-1", title="S1", index=2, show=show)
    show.attach_children(episodes=[], seasons=[season])

    identifier = ItemIdentifier.from_item(cast(Any, season))

    assert identifier.parent_title == "Show"
    assert identifier.season_index == 2
    assert identifier.item_type == "season"


def test_item_identifier_from_items_handles_collections() -> None:
    """``from_items`` maps each media item into an identifier."""
    show = FakeLibraryShow(key="show-1", title="Show")
    season = FakeLibrarySeason(key="season-1", title="S1", index=1, show=show)
    episode = FakeLibraryEpisode(
        key="ep-1",
        title="Episode 1",
        index=1,
        season_index=1,
        show=show,
        season=season,
    )
    show.attach_children(episodes=[episode], seasons=[season])

    identifiers = ItemIdentifier.from_items([cast(LibraryEpisodeProtocol, episode)])

    assert len(identifiers) == 1
    assert identifiers[0].rating_key == "ep-1"


def test_item_identifier_rejects_unknown_media_kind() -> None:
    """Unsupported media kinds raise ``UnsupportedMediaTypeError``."""
    weird_media = SimpleNamespace(
        key="weird",
        title="Weird",
        media_kind=SimpleNamespace(value="mystery"),
    )

    with pytest.raises(UnsupportedMediaTypeError):
        ItemIdentifier.from_item(cast(Any, weird_media))


def test_entry_snapshot_round_trip(list_entry: ListEntryProtocol) -> None:
    """Snapshots capture list entry state and serialize to JSON primitives."""
    snapshot = EntrySnapshot.from_entry(list_entry)
    as_dict = snapshot.to_dict()
    assert as_dict["media_key"] == "42"
    assert as_dict["status"] == ListStatus.CURRENT
    assert as_dict["progress"] == 6

    serialized = snapshot.serialize()
    assert serialized["started_at"] == "2025-01-01T00:00:00+00:00"
    assert serialized["finished_at"] is None

    reconstructed = EntrySnapshot.from_dict(serialized)
    assert reconstructed.status == ListStatus.CURRENT
    assert reconstructed.progress == 6


def test_sync_stats_tracking_and_counts() -> None:
    """SyncStats tracks per-item outcomes and aggregates counts/coverage."""
    pending_item = ItemIdentifier(
        rating_key="pending",
        title="Pending",
        item_type="movie",
    )
    synced_item = ItemIdentifier(
        rating_key="synced",
        title="Synced",
        item_type="movie",
    )
    stats = SyncStats()
    stats.register_pending_items([pending_item])
    stats.track_item(synced_item, SyncOutcome.SYNCED)
    stats.track_items([pending_item], SyncOutcome.SKIPPED)
    stats.track_item(
        ItemIdentifier(rating_key="episode", title="E1", item_type="episode"),
        SyncOutcome.SYNCED,
    )

    assert stats.synced == 1
    assert stats.skipped == 1
    assert stats.pending == 0
    assert stats.total_items == 2
    assert stats.coverage == 1.0


def test_sync_stats_untrack_items() -> None:
    """Untracking removes entries from outcome maps."""
    stats = SyncStats()
    movie = ItemIdentifier(rating_key="1", title="Movie", item_type="movie")
    show = ItemIdentifier(rating_key="2", title="Show", item_type="show")
    stats.track_items([movie, show], SyncOutcome.FAILED)

    stats.untrack_item(movie)
    stats.untrack_items([show])

    assert stats.total_items == 0


def test_sync_stats_get_items_by_outcome_filters_types() -> None:
    """Grandchild items are excluded from top-level item queries."""
    stats = SyncStats()
    show_item = ItemIdentifier(rating_key="show", title="Show", item_type="show")
    episode_item = ItemIdentifier(
        rating_key="episode",
        title="E1",
        item_type="episode",
    )
    stats.track_item(show_item, SyncOutcome.SYNCED)
    stats.track_item(episode_item, SyncOutcome.SYNCED)

    top_level = stats.get_items_by_outcome()
    assert show_item in top_level
    assert episode_item not in top_level


def test_sync_stats_not_found_and_total_processed() -> None:
    """Derived properties aggregate multiple outcomes."""
    stats = SyncStats()
    stats.track_item(
        ItemIdentifier(rating_key="nf", title="Missing", item_type="movie"),
        SyncOutcome.NOT_FOUND,
    )
    stats.track_item(
        ItemIdentifier(rating_key="fail", title="Fail", item_type="movie"),
        SyncOutcome.FAILED,
    )

    assert stats.not_found == 1
    assert stats.total_processed == 2


def test_sync_stats_coverage_handles_no_grandchildren() -> None:
    """When no episodes are tracked, coverage defaults to 100%."""
    stats = SyncStats()
    assert stats.coverage == 1.0


def test_sync_stats_combine_merges_maps() -> None:
    """Combining stats merges the tracked outcome dictionaries."""
    stats_a = SyncStats()
    stats_b = SyncStats()
    item_a = ItemIdentifier(rating_key="a", title="A", item_type="movie")
    item_b = ItemIdentifier(rating_key="b", title="B", item_type="movie")
    stats_a.track_item(item_a, SyncOutcome.FAILED)
    stats_b.track_item(item_b, SyncOutcome.DELETED)

    combined = stats_a + stats_b

    assert combined.failed == 1
    assert combined.deleted == 1
    assert combined.total_items == 2
