"""Focused tests for helper routines within the mappings service."""

from contextlib import contextmanager
from typing import cast

import pytest

from src.config.database import db
from src.models.db.animap import AniMap
from src.models.db.provenance import AniMapProvenance
from src.web.services.mappings_service import MappingsService


@contextmanager
def _fresh_animap_table():
    with db() as ctx:
        ctx.session.query(AniMapProvenance).delete()
        ctx.session.query(AniMap).delete()
        ctx.session.commit()
    try:
        yield
    finally:
        with db() as ctx:
            ctx.session.query(AniMapProvenance).delete()
            ctx.session.query(AniMap).delete()
            ctx.session.commit()


def _insert_animap(**kwargs) -> None:
    payload = {
        "anilist_id": kwargs.get("anilist_id", 1),
        "anidb_id": kwargs.get("anidb_id", 111),
        "imdb_id": kwargs.get("imdb_id", ["tt1", "tt2"]),
        "mal_id": kwargs.get("mal_id", [123]),
        "tmdb_movie_id": kwargs.get("tmdb_movie_id", [456]),
        "tmdb_show_id": kwargs.get("tmdb_show_id", 789),
        "tvdb_id": kwargs.get("tvdb_id", 987),
        "tmdb_mappings": kwargs.get("tmdb_mappings", {"s1": "e1-e2"}),
        "tvdb_mappings": kwargs.get("tvdb_mappings", {"s1": "e1-e2"}),
    }
    with db() as ctx:
        ctx.session.add(AniMap(**payload))
        ctx.session.commit()


def test_parse_numeric_filters_and_normalizers():
    """Numeric helper parses comparison and ranges for AniList filters."""
    service = MappingsService()
    cmp_filter, range_filter, raw = service._parse_numeric_filters(">=10")
    assert cmp_filter == (">=", 10)
    assert range_filter is None
    assert raw == ">=10"

    cmp_filter, range_filter, _ = service._parse_numeric_filters("5..15")
    assert range_filter == (5, 15)
    assert cmp_filter is None

    assert service._normalize_text_query("Title* ") == "Title"


def test_build_anilist_term_filters_for_strings_and_enums():
    """String and enum query fields produce the correct GraphQL filters."""
    service = MappingsService()
    field_map = service._FIELD_MAP
    title_spec = field_map["anilist.title"]
    filters = service._build_anilist_term_filters(title_spec, "  Foo Bar  ")
    assert filters == {"search": "Foo Bar"}

    status_spec = field_map["anilist.status"]
    filters = service._build_anilist_term_filters(
        status_spec,
        "FINISHED",
        multi_values=("FINISHED", "RELEASING"),
    )
    assert filters == {"status_in": ["FINISHED", "RELEASING"]}

    numeric_spec = field_map["anilist.average_score"]
    filters = service._build_anilist_term_filters(numeric_spec, "10..20")
    assert filters["averageScore_greater"] == 9
    assert filters["averageScore_lesser"] == 21


def test_scalar_and_json_filters_against_database_rows():
    """Scalar/JSON helper methods return AniList identifiers for matches."""
    service = MappingsService()
    with _fresh_animap_table():
        _insert_animap()
        with db() as ctx:
            cmp_filter, range_filter, raw = service._parse_numeric_filters("111")
            result = service._filter_scalar(
                ctx,
                AniMap.anidb_id,
                cmp_filter,
                range_filter,
                raw,
            )
            assert result == {1}

            result = service._filter_json_array(
                ctx,
                AniMap.imdb_id,
                numeric=False,
                raw_value="tt1",
                cmp_filter=None,
                range_filter=None,
            )
            assert result == {1}

            result = service._filter_json_dict(ctx, AniMap.tmdb_mappings, "s1")
            assert result == {1}

            has_ids = service._resolve_has(ctx, "imdb")
            assert has_ids == {1}


def test_build_item_and_custom_detection():
    """Custom detection depends on the upstream URL and provenance sources."""
    service = MappingsService()
    service.upstream_url = "https://example"
    assert service._is_custom_source(["https://example"]) is False
    assert service._is_custom_source(["custom"]) is True

    class DummyAnimap:
        def __init__(self) -> None:
            self.anilist_id = 1
            self.anidb_id = 2
            self.imdb_id = ["tt1"]
            self.mal_id = [3]
            self.tmdb_movie_id = [4]
            self.tmdb_show_id = 5
            self.tvdb_id = 6
            self.tmdb_mappings = {"s1": "e1-e2"}
            self.tvdb_mappings = {"s1": "e1-e2"}

    item = service._build_item(1, cast(AniMap, DummyAnimap()), ["custom"])
    assert item["custom"] is True


@pytest.mark.asyncio
async def test_list_mappings_without_query_filters():
    """list_mappings paginates results and collects provenance data."""
    service = MappingsService()
    with _fresh_animap_table():
        _insert_animap(anilist_id=1)
        _insert_animap(anilist_id=2, anidb_id=222)
        with db() as ctx:
            ctx.session.add_all(
                [
                    AniMapProvenance(anilist_id=1, n=1, source="custom"),
                    AniMapProvenance(anilist_id=2, n=1, source="upstream"),
                ]
            )
            ctx.session.commit()

        items, total = await service.list_mappings(
            page=1,
            per_page=10,
            q=None,
            custom_only=False,
            with_anilist=False,
        )
        assert total == 2
        assert [item["anilist_id"] for item in items] == [1, 2]
