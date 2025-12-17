"""Tests for the Animap client (descriptor graph)."""

import asyncio
import importlib
import json
from hashlib import md5
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import select

from src.config.database import AniBridgeDB
from src.core.animap import AnimapClient, AnimapEdge, MappingDescriptor
from src.core.mappings import MappingsClient
from src.models.db.animap import AnimapEntry, AnimapMapping, AnimapProvenance
from src.models.db.base import Base
from src.models.db.housekeeping import Housekeeping


class FakeMappingsClient:
    """Lightweight stub for the mappings client used during tests."""

    def __init__(
        self,
        mappings: dict[str, Any],
        provenance: dict[str, list[str]],
    ) -> None:
        """Initialize the fake client with predefined mappings and provenance."""
        self.mappings = mappings
        self.provenance = provenance
        self.load_calls = 0

    async def load_mappings(self) -> dict[str, Any]:
        """Return the predefined mappings."""
        self.load_calls += 1
        return self.mappings

    def get_provenance(self) -> dict[str, list[str]]:
        """Return the predefined provenance."""
        return self.provenance

    async def close(self) -> None:
        """No-op for closing the fake client."""
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
) -> AnimapClient:
    """Provide an AnimapClient instance for testing."""
    client = AnimapClient(data_path=tmp_path, upstream_url=None)

    def _finalize() -> None:
        asyncio.run(client.close())

    request.addfinalizer(_finalize)
    return client


def _mapping_data():
    return {
        "anilist:1:movie": {"tmdb:10:movie": {"1": None}},
        "anilist:2:s1": {"tvdb:20:s1": {"s1": "e1-e12"}},
    }


def _write_mapping_file(base: Path, data: dict) -> Path:
    mappings_path = base / "mappings.json"
    mappings_path.write_text(json.dumps(data), encoding="utf-8")
    return mappings_path


def _fetch_edges(ctx) -> list[AnimapEdge]:
    entries = {
        entry.id: entry for entry in ctx.session.execute(select(AnimapEntry)).scalars()
    }
    mappings = ctx.session.execute(select(AnimapMapping)).scalars().all()
    edges: list[AnimapEdge] = []
    for mapping in mappings:
        src = entries[mapping.source_entry_id]
        dst = entries[mapping.destination_entry_id]
        edges.append(
            AnimapEdge(
                source=cast(
                    MappingDescriptor,
                    SimpleNamespace(
                        provider=src.provider,
                        entry_id=src.entry_id,
                        scope=src.entry_scope,
                    ),
                ),
                destination=cast(
                    MappingDescriptor,
                    SimpleNamespace(
                        provider=dst.provider,
                        entry_id=dst.entry_id,
                        scope=dst.entry_scope,
                    ),
                ),
                source_range=mapping.source_range,
                destination_range=mapping.destination_range,
            )
        )
    return edges


def test_sync_db_creates_entries_mappings_and_provenance(
    animap_client: AnimapClient, tmp_path: Path, in_memory_db: AniBridgeDB
) -> None:
    """Syncing the database creates entries, mappings, and provenance rows."""
    mapping_data = _mapping_data()
    mappings_path = _write_mapping_file(tmp_path, mapping_data)

    asyncio.run(animap_client.sync_db())

    expected_hash = md5(json.dumps(mapping_data, sort_keys=True).encode()).hexdigest()

    with in_memory_db as ctx:
        entries = (
            ctx.session.execute(
                select(AnimapEntry).order_by(AnimapEntry.provider, AnimapEntry.entry_id)
            )
            .scalars()
            .all()
        )
        provenance_rows = (
            ctx.session.execute(
                select(AnimapProvenance).order_by(
                    AnimapProvenance.mapping_id, AnimapProvenance.n
                )
            )
            .scalars()
            .all()
        )
        hash_entry = ctx.session.get(Housekeeping, "animap_mappings_hash")
        edges = _fetch_edges(ctx)

    assert hash_entry is not None
    assert hash_entry.value == expected_hash

    assert {(e.provider, e.entry_id, e.entry_scope) for e in entries} == {
        ("anilist", "1", "movie"),
        ("tmdb", "10", "movie"),
        ("anilist", "2", "s1"),
        ("tvdb", "20", "s1"),
    }

    edge_keys = {
        (
            edge.source.provider,
            edge.source.entry_id,
            edge.source.scope,
            edge.destination.provider,
            edge.destination.entry_id,
            edge.destination.scope,
            edge.source_range,
            edge.destination_range,
        )
        for edge in edges
    }
    assert edge_keys == {
        ("anilist", "1", "movie", "tmdb", "10", "movie", "1", None),
        ("anilist", "2", "s1", "tvdb", "20", "s1", "s1", "e1-e12"),
        ("tvdb", "20", "s1", "anilist", "2", "s1", "e1-e12", "s1"),
    }

    expected_source = str(mappings_path.resolve())
    assert [row.source for row in provenance_rows] == [
        expected_source,
        expected_source,
        expected_source,
    ]
    assert [row.n for row in provenance_rows] == [0, 0, 0]


def test_get_graph_for_ids_returns_edges_for_providers(
    animap_client: AnimapClient, tmp_path: Path, in_memory_db: AniBridgeDB
) -> None:
    """Getting the mapping graph for IDs returns the correct edges."""
    _write_mapping_file(tmp_path, _mapping_data())
    asyncio.run(animap_client.sync_db())

    edges = animap_client.get_graph_for_ids({"anilist": "1"}).edges
    assert len(edges) == 1
    assert edges[0].source.provider == "anilist"
    assert edges[0].destination.provider == "tmdb"

    tvdb_edges = animap_client.get_graph_for_ids({"tvdb": "20"}).edges
    assert {
        (
            e.source.provider,
            e.destination.provider,
            e.source_range,
            e.destination_range,
        )
        for e in tvdb_edges
    } == {
        ("tvdb", "anilist", "e1-e12", "s1"),
        ("anilist", "tvdb", "s1", "e1-e12"),
    }


def test_sync_db_refreshes_provenance_when_hash_matches(
    animap_client: AnimapClient, in_memory_db: AniBridgeDB
) -> None:
    """Syncing the database again with the same mappings refreshes provenance."""
    base_mappings = {"anilist:1:movie": {"tmdb:1:movie": {"1": None}}}
    fake_client = FakeMappingsClient(
        mappings=base_mappings,
        provenance={"anilist:1:movie": ["/initial.json"]},
    )
    animap_client.mappings_client = cast(MappingsClient, fake_client)
    asyncio.run(animap_client.sync_db())

    fake_client.provenance = {"anilist:1:movie": ["/updated.json", "/extra.json"]}
    asyncio.run(animap_client.sync_db())

    with in_memory_db as ctx:
        provenance_rows = (
            ctx.session.execute(
                select(AnimapProvenance).order_by(
                    AnimapProvenance.mapping_id, AnimapProvenance.n
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
