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
async def test_custom_only_applies_before_pagination() -> None:
    """Custom-only filtering happens before pagination slices results."""
    service = MappingsService()
    with _fresh_tables():
        with db() as ctx:
            upstream_entry = AnimapEntry(
                provider="aaa", entry_id="1", entry_scope="movie"
            )
            upstream_target = AnimapEntry(
                provider="dest", entry_id="1", entry_scope="movie"
            )
            custom_entry = AnimapEntry(
                provider="zzz", entry_id="1", entry_scope="movie"
            )
            custom_target = AnimapEntry(
                provider="dest", entry_id="2", entry_scope="movie"
            )
            ctx.session.add_all(
                [upstream_entry, upstream_target, custom_entry, custom_target]
            )
            ctx.session.flush()

            upstream_mapping = AnimapMapping(
                source_entry_id=upstream_entry.id,
                destination_entry_id=upstream_target.id,
                source_range="1",
                destination_range=None,
            )
            custom_mapping = AnimapMapping(
                source_entry_id=custom_entry.id,
                destination_entry_id=custom_target.id,
                source_range="1",
                destination_range=None,
            )
            ctx.session.add_all([upstream_mapping, custom_mapping])
            ctx.session.flush()

            upstream_source = service.upstream_url or "upstream"
            ctx.session.add(
                AnimapProvenance(
                    mapping_id=upstream_mapping.id, n=0, source=upstream_source
                )
            )
            ctx.session.add(
                AnimapProvenance(mapping_id=custom_mapping.id, n=0, source="custom")
            )
            ctx.session.commit()

        items, total = await service.list_mappings(
            page=1, per_page=1, q=None, custom_only=True
        )

        assert total == 1
        assert len(items) == 1
        assert items[0]["descriptor"] == (
            f"{custom_entry.provider}:{custom_entry.entry_id}:{custom_entry.entry_scope}"
        )


@pytest.mark.asyncio
async def test_filter_custom_entry_ids_batches() -> None:
    """Custom filtering handles large ID sets without exceeding SQL var limits."""
    service = MappingsService()
    with _fresh_tables():
        total_entries = 1200
        with db() as ctx:
            entries: list[AnimapEntry] = []
            for idx in range(total_entries):
                entry = AnimapEntry(
                    provider=f"p{idx:04d}", entry_id=str(idx), entry_scope="movie"
                )
                target = AnimapEntry(
                    provider="t", entry_id=str(idx), entry_scope="movie"
                )
                ctx.session.add_all([entry, target])
                entries.append(entry)
            ctx.session.flush()

            mappings: list[AnimapMapping] = []
            for entry in entries:
                target = (
                    ctx.session.query(AnimapEntry)
                    .filter_by(provider="t", entry_id=entry.entry_id)
                    .one()
                )
                mapping = AnimapMapping(
                    source_entry_id=entry.id,
                    destination_entry_id=target.id,
                    source_range="1",
                    destination_range=None,
                )
                mappings.append(mapping)
            ctx.session.add_all(mappings)
            ctx.session.flush()

            for n, mapping in enumerate(mappings):
                source = (
                    "custom" if n % 2 == 0 else (service.upstream_url or "upstream")
                )
                ctx.session.add(
                    AnimapProvenance(mapping_id=mapping.id, n=0, source=source)
                )
            ctx.session.commit()

            entry_ids = [e.id for e in entries]

        custom_ids = service._filter_custom_entry_ids(entry_ids)

        assert len(custom_ids) == total_entries // 2 + total_entries % 2


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
