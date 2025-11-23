"""Tests for the AniMap client."""

import asyncio
import importlib
import json
from hashlib import md5
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.config.database import AniBridgeDB
from src.core.animap import AniMapClient
from src.core.mappings import MappingsClient
from src.models.db.animap import AniMap
from src.models.db.base import Base
from src.models.db.housekeeping import Housekeeping
from src.models.db.provenance import AniMapProvenance


class FakeMappingsClient:
    """Lightweight stub for the mappings client used during tests."""

    def __init__(
        self,
        mappings: dict[str, Any],
        provenance: dict[int, list[str]],
    ) -> None:
        """Store static mappings and provenance data for reuse across syncs."""
        self.mappings = mappings
        self.provenance = provenance
        self.load_calls = 0

    async def load_mappings(self) -> dict[str, Any]:
        """Return the preconfigured mappings without hitting the filesystem."""
        self.load_calls += 1
        return self.mappings

    def get_provenance(self) -> dict[int, list[str]]:
        """Return the captured provenance map for the stubbed mappings."""
        return self.provenance

    async def close(self) -> None:
        """Mirror the async close contract of the real client."""
        return None


@pytest.fixture
def in_memory_db(monkeypatch: pytest.MonkeyPatch):
    """Provide an in-memory database patched into the application."""
    engine = create_engine("sqlite:///:memory:", future=True)

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )

    class _DB:
        def __init__(self) -> None:
            self._session = None

        def __enter__(self):
            self._session = session_factory()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            if self._session is not None:
                self._session.close()
                self._session = None

        @property
        def session(self):
            if self._session is None:
                self._session = session_factory()
            return self._session

    db_instance = _DB()

    database_module = importlib.import_module("src.config.database")
    animap_module = importlib.import_module("src.core.animap")

    monkeypatch.setattr(database_module, "db", lambda: db_instance)
    monkeypatch.setattr(animap_module, "db", lambda: db_instance)

    try:
        yield db_instance
    finally:
        session = getattr(db_instance, "_session", None)
        if session is not None:
            session.close()
        engine.dispose()


@pytest.fixture
def animap_client(
    tmp_path: Path, in_memory_db: AniBridgeDB, request: pytest.FixtureRequest
) -> AniMapClient:
    """Provide an AniMapClient instance for testing."""
    client = AniMapClient(data_path=tmp_path, upstream_url=None)

    def _finalize() -> None:
        asyncio.run(client.close())

    request.addfinalizer(_finalize)
    return client


def test_sync_db_creates_rows_and_provenance(
    animap_client: AniMapClient, tmp_path: Path, in_memory_db: AniBridgeDB
):
    """Test that sync_db creates AniMap and provenance rows correctly."""
    mapping_data = {
        "1": {
            "imdb_id": "tt12345",
            "tmdb_movie_id": 54321,
        },
        "2": {
            "tvdb_id": 777,
            "tmdb_show_id": 678,
            "tmdb_mappings": {"s1": "e1-e12"},
        },
    }

    mappings_path = tmp_path / "mappings.custom.json"
    mappings_path.write_text(json.dumps(mapping_data), encoding="utf-8")

    asyncio.run(animap_client.sync_db())

    expected_hash = md5(json.dumps(mapping_data, sort_keys=True).encode()).hexdigest()

    with in_memory_db as ctx:
        rows = (
            ctx.session.execute(select(AniMap).order_by(AniMap.anilist_id))
            .scalars()
            .all()
        )
        provenance_rows = (
            ctx.session.execute(
                select(AniMapProvenance).order_by(
                    AniMapProvenance.anilist_id, AniMapProvenance.n
                )
            )
            .scalars()
            .all()
        )
        hash_entry = ctx.session.get(Housekeeping, "animap_mappings_hash")

    assert hash_entry is not None
    assert hash_entry.value == expected_hash

    assert [row.anilist_id for row in rows] == [1, 2]
    assert rows[0].imdb_id == ["tt12345"]
    assert rows[0].tmdb_movie_id == [54321]
    assert rows[1].tvdb_id == 777
    assert rows[1].tmdb_show_id == 678
    assert rows[1].tmdb_mappings == {"s1": "e1-e12"}

    sources = [row.source for row in provenance_rows]
    expected_source = str(mappings_path.resolve())
    assert sources == [expected_source, expected_source]
    assert [row.n for row in provenance_rows] == [0, 0]


def test_get_mappings_filters_by_identifiers(
    animap_client: AniMapClient, tmp_path: Path, in_memory_db: AniBridgeDB
):
    """Test that get_mappings filters AniMap rows by provided identifiers."""
    mapping_data = {
        "10": {
            "imdb_id": ["tt99999", "tt11111"],
            "tmdb_movie_id": [111, 222],
        },
        "20": {
            "imdb_id": "tt22222",
            "tmdb_show_id": 333,
            "tvdb_id": 444,
        },
    }

    (tmp_path / "mappings.custom.json").write_text(
        json.dumps(mapping_data),
        encoding="utf-8",
    )

    asyncio.run(animap_client.sync_db())

    movie_matches = list(animap_client.get_mappings(imdb="tt99999"))
    tmdb_matches = list(animap_client.get_mappings(tmdb=222))
    tvdb_matches = list(animap_client.get_mappings(tvdb=444))
    tmdb_show_matches = list(animap_client.get_mappings(tmdb=[999, 333]))
    empty_matches = list(animap_client.get_mappings())

    assert {row.anilist_id for row in movie_matches} == {10}
    assert {row.anilist_id for row in tmdb_matches} == {10}
    assert movie_matches[0].imdb_id == ["tt99999", "tt11111"]

    assert {row.anilist_id for row in tvdb_matches} == {20}
    assert {row.anilist_id for row in tmdb_show_matches} == {20}
    assert empty_matches == []


def test_get_mappings_returns_empty_when_no_identifiers(
    animap_client: AniMapClient,
):
    """Ensure get_mappings short-circuits when no identifiers are provided."""
    assert list(animap_client.get_mappings()) == []


def test_sync_db_filters_invalid_entries(
    animap_client: AniMapClient, in_memory_db: AniBridgeDB
):
    """Invalid mapping entries are ignored while null overrides are preserved."""
    fake_client = FakeMappingsClient(
        mappings={
            "1": {"imdb_id": "ttvalid"},
            "2": "not-a-dict",
            "3": None,
        },
        provenance={1: ["/source.json"], 3: ["/source.json"]},
    )
    animap_client.mappings_client = cast(MappingsClient, fake_client)
    asyncio.run(animap_client.sync_db())

    with in_memory_db as ctx:
        rows = (
            ctx.session.execute(select(AniMap).order_by(AniMap.anilist_id))
            .scalars()
            .all()
        )
        ids = [row.anilist_id for row in rows]
        assert ids == [1, 3]
        assert rows[0].imdb_id == ["ttvalid"]
        assert rows[1].imdb_id is None

        provenance_rows = (
            ctx.session.execute(
                select(AniMapProvenance).order_by(
                    AniMapProvenance.anilist_id, AniMapProvenance.n
                )
            )
            .scalars()
            .all()
        )

    assert [row.source for row in provenance_rows] == ["/source.json", "/source.json"]
    assert [row.anilist_id for row in provenance_rows] == [1, 3]


def test_sync_db_refreshes_provenance_when_hash_matches(
    animap_client: AniMapClient, in_memory_db: AniBridgeDB
):
    """When hashes match, the sync still refreshes provenance rows."""
    fake_client = FakeMappingsClient(
        mappings={"1": {"imdb_id": "tt001"}},
        provenance={1: ["/initial.json"]},
    )
    animap_client.mappings_client = cast(MappingsClient, fake_client)
    asyncio.run(animap_client.sync_db())

    fake_client.provenance = {1: ["/updated.json", "/extra.json"]}
    asyncio.run(animap_client.sync_db())

    with in_memory_db as ctx:
        provenance_rows = (
            ctx.session.execute(
                select(AniMapProvenance).order_by(
                    AniMapProvenance.anilist_id, AniMapProvenance.n
                )
            )
            .scalars()
            .all()
        )
        housekeeping = ctx.session.get(Housekeeping, "animap_mappings_hash")

    assert housekeeping is not None
    assert [row.source for row in provenance_rows] == [
        "/updated.json",
        "/extra.json",
    ]
    assert [row.n for row in provenance_rows] == [0, 1]
