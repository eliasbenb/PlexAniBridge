"""Lightweight tests for mappings query specs (v3)."""

from src.web.services.mappings_query_spec import get_query_field_map


def test_query_field_map_contains_core_fields() -> None:
    """The mappings query field map contains core fields."""
    field_map = get_query_field_map()
    assert set(field_map.keys()) == {"provider", "entry_id", "scope"}
    assert field_map["provider"].desc == "Source provider"
