"""Tests for v3 mappings service (provider-range graph)."""

from contextlib import contextmanager

import pytest

from src.config.database import db
from src.models.db.animap import AnimapEntry, AnimapMapping, AnimapProvenance
from src.web.services.mappings_service import MappingsService


@contextmanager
def _fresh_tables():
    with db() as ctx:
        ctx.session.query(AnimapProvenance).delete()
        ctx.session.query(AnimapMapping).delete()
        ctx.session.query(AnimapEntry).delete()
        ctx.session.commit()
    try:
        yield
    finally:
        with db() as ctx:
            ctx.session.query(AnimapProvenance).delete()
            ctx.session.query(AnimapMapping).delete()
            ctx.session.query(AnimapEntry).delete()
            ctx.session.commit()


def _seed_graph():
    with db() as ctx:
        a = AnimapEntry(provider="anilist", entry_id="1", entry_scope="movie")
        b = AnimapEntry(provider="tmdb", entry_id="10", entry_scope="movie")
        ctx.session.add_all([a, b])
        ctx.session.flush()
        mapping = AnimapMapping(
            source_entry_id=a.id,
            destination_entry_id=b.id,
            source_range="1",
            destination_range=None,
        )
        ctx.session.add(mapping)
        ctx.session.flush()
        ctx.session.add(AnimapProvenance(mapping_id=mapping.id, n=0, source="custom"))
        ctx.session.commit()


@pytest.mark.asyncio
async def test_list_mappings_returns_edges_and_sources() -> None:
    """Listing mappings returns items with edges and source info."""
    service = MappingsService()
    with _fresh_tables():
        _seed_graph()
        items, total = await service.list_mappings(
            page=1, per_page=10, q=None, custom_only=False
        )
        assert total == 2
        descriptors = {item["descriptor"] for item in items}
        assert "anilist:1:movie" in descriptors
        assert any(edge["target_provider"] == "tmdb" for edge in items[0]["edges"])


@pytest.mark.asyncio
async def test_get_mapping_filters_by_descriptor() -> None:
    """Getting a mapping by descriptor returns the correct item."""
    service = MappingsService()
    with _fresh_tables():
        _seed_graph()
        item = await service.get_mapping("anilist:1:movie")
        assert item["descriptor"] == "anilist:1:movie"
        assert item["edges"][0]["target_provider"] == "tmdb"


@pytest.mark.asyncio
async def test_custom_only_filters_items() -> None:
    """Listing mappings with custom_only filters out non-custom items."""
    service = MappingsService()
    with _fresh_tables():
        _seed_graph()
        # Add upstream provenance to second mapping to mark non-custom
        with db() as ctx:
            tmdb_entry = ctx.session.query(AnimapEntry).filter_by(provider="tmdb").one()
            anilist_entry = (
                ctx.session.query(AnimapEntry).filter_by(provider="anilist").one()
            )
            mapping = AnimapMapping(
                source_entry_id=tmdb_entry.id,
                destination_entry_id=anilist_entry.id,
                source_range="1",
                destination_range=None,
            )
            ctx.session.add(mapping)
            ctx.session.flush()
            ctx.session.add(
                AnimapProvenance(mapping_id=mapping.id, n=0, source="upstream")
            )
            ctx.session.commit()

        items, _ = await service.list_mappings(
            page=1, per_page=10, q=None, custom_only=True
        )
        assert all(item["custom"] for item in items)


@pytest.mark.asyncio
async def test_search_by_entry_id() -> None:
    """Booru query supports filtering by Animap entry ID."""
    service = MappingsService()
    with _fresh_tables():
        _seed_graph()
        with db() as ctx:
            entry_id = (
                ctx.session.query(AnimapEntry.id)
                .filter(AnimapEntry.provider == "anilist")
                .scalar()
            )

        items, total = await service.list_mappings(
            page=1, per_page=10, q=f"id:{entry_id}", custom_only=False
        )

        assert total == 1
        assert len(items) == 1
        assert items[0]["descriptor"].startswith("anilist:")
