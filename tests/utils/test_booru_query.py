"""Tests for the booru query parser and evaluator."""

import pytest

from src.exceptions import BooruQuerySyntaxError
from src.utils import booru_query as bq


def test_parse_query_returns_empty_and_for_blank_string():
    """Test that parsing a blank string returns an empty And node."""
    node = bq.parse_query("   ")
    assert isinstance(node, bq.And)
    assert node.children == []


def test_parse_query_invalid_raises_custom_error():
    """Test that parsing an invalid query raises a BooruQuerySyntaxError."""
    with pytest.raises(BooruQuerySyntaxError):
        bq.parse_query("foo:(")
    with pytest.raises(BooruQuerySyntaxError):
        bq.parse_query('unclosed "quote')
    with pytest.raises(BooruQuerySyntaxError):
        bq.parse_query("foo | | bar")


def test_collect_helpers_preserve_order_and_deduplicate():
    """Test that collect_bare_terms preserves order and deduplicates terms."""
    node = bq.parse_query('"naruto" anilist.genre:action -"bleach" "naruto"')

    bare_terms = bq.collect_bare_terms(node)
    assert bare_terms == ["naruto", "bleach"]

    key_terms = bq.collect_key_terms(node)
    assert [f"{term.key}:{term.value}" for term in key_terms] == [
        "anilist.genre:action",
    ]


def test_parse_query_auto_groups_unquoted_terms_into_phrase():
    """Unquoted multi-word AniList searches should auto-merge into one term."""
    node = bq.parse_query("Full Metal Panic")

    assert isinstance(node, bq.BareTerm)
    assert node.text == "Full Metal Panic"
    assert node.quoted is False


def test_parse_query_merges_phrase_alongside_filters():
    """Ensure filters with trailing phrase auto-merge remaining bare terms."""
    node = bq.parse_query("anilist.status:FINISHED Full Metal Panic")

    assert isinstance(node, bq.And)
    assert len(node.children) == 2
    assert isinstance(node.children[0], bq.KeyTerm)
    assert isinstance(node.children[1], bq.BareTerm)
    assert node.children[1].text == "Full Metal Panic"


def test_parse_query_keeps_or_terms_separate():
    """OR-separated AniList terms should remain distinct."""
    node = bq.parse_query("Naruto | Shippuden")

    assert isinstance(node, bq.Or)
    assert all(isinstance(term, bq.BareTerm) for term in node.children)
    texts = [term.text for term in node.children if isinstance(term, bq.BareTerm)]
    assert texts == ["Naruto", "Shippuden"]


def test_evaluate_combines_or_group_with_and_filters():
    """Test that evaluate combines OR groups with AND filters."""
    node = bq.parse_query('~"Naruto" ~"Bleach" anilist.genre:action')

    def db_resolver(key: str, value: str) -> set[int]:
        mapping = {
            ("anilist.genre", "action"): {1, 2},
            ("anilist.genre", "drama"): {2, 3},
        }
        return set(mapping.get((key, value), set()))

    def anilist_resolver(term: str) -> list[int]:
        mapping = {
            "Naruto": [1, 3],
            "Bleach": [4, 1],
        }
        return list(mapping.get(term, []))

    result = bq.evaluate(
        node,
        db_resolver=db_resolver,
        anilist_resolver=anilist_resolver,
        universe_ids={1, 2, 3, 4},
    )

    assert result.ids == {1}
    assert result.used_bare is True
    assert result.order_hint[1] == 0
    assert result.order_hint[4] == 0


def test_evaluate_not_uses_provided_universe():
    """Test that NOT queries use the provided universe of IDs."""
    node = bq.parse_query("-anilist.genre:action")

    def db_resolver(key: str, value: str) -> set[int]:
        if (key, value) == ("anilist.genre", "action"):
            return {2, 3}
        return set()

    result = bq.evaluate(
        node,
        db_resolver=db_resolver,
        anilist_resolver=lambda _term: [],
        universe_ids={1, 2, 3},
    )

    assert result.ids == {1}
    assert result.used_bare is False
    assert result.order_hint == {}
