"""Tests covering AniList filter construction for mappings service."""

import pytest

from src.exceptions import AniListFilterError
from src.web.services.mappings_query_spec import get_query_field_map
from src.web.services.mappings_service import MappingsService


@pytest.fixture(scope="module")
def mappings_service() -> MappingsService:
    """Provide a MappingsService instance for filter tests."""
    return MappingsService()


def test_build_anilist_filters_multi_string(mappings_service: MappingsService) -> None:
    """Multiple AniList string values should map to *_in filters."""
    spec = get_query_field_map()["anilist.genre"]
    filters = mappings_service._build_anilist_term_filters(
        spec,
        "Action,Drama",
        ("Action", "Drama"),
    )
    assert filters == {"genre_in": ["Action", "Drama"]}


def test_build_anilist_filters_multi_enum(mappings_service: MappingsService) -> None:
    """Multiple AniList enum values should resolve and deduplicate."""
    spec = get_query_field_map()["anilist.format"]
    filters = mappings_service._build_anilist_term_filters(
        spec,
        "TV,Movie,TV",
        ("tv", "Movie", "TV"),
    )
    assert filters == {"format_in": ["TV", "MOVIE"]}


def test_build_anilist_filters_multi_not_supported(
    mappings_service: MappingsService,
) -> None:
    """Fields without *_in support should raise when given multiple values."""
    spec = get_query_field_map()["anilist.title"]
    with pytest.raises(AniListFilterError):
        mappings_service._build_anilist_term_filters(
            spec,
            "Naruto,Bleach",
            ("Naruto", "Bleach"),
        )
