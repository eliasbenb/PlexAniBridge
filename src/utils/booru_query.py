"""Booru-like query parsing and evaluation.

This module defines a booru-like query language using pyparsing and provides helpers to
evaluate the parsed AST into a set of AniList IDs.

Supported syntax:
- Value search terms: `foo:bar` search for `bar` in field `foo`
- AniList search terms: `"foo"` search the AniList API for the bare term 'foo'
- AND: `foo bar` search for the intersection of both terms
- OR (prefix): `~foo ~bar baz` search for `(foo OR bar) AND baz` - tilde marks terms
    for OR grouping within AND
- OR (infix): `foo | bar baz` search for `foo OR (bar AND baz)` - pipe creates OR
    between AND expressions
- NOT: `-foo` search the negation of `foo`
- Grouping: `(foo | bar) baz` search for `(foo OR bar) AND baz`
- Ranges: `foo:<10 | foo:100..210` search for foo less than 10 or between 100 and 210
"""

# TODO: Support `has:foo` queries

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pyparsing as pp

pp.ParserElement.enablePackrat()  # Supposed to speed up parsing

DbResolver = Callable[[str, str], set[int]]
AniListResolver = Callable[[str], list[int]]


class Node:
    """Base AST node for booru-like queries."""


@dataclass
class KeyTerm(Node):
    """A key:value term that targets the local DB."""

    key: str
    value: str


@dataclass
class BareTerm(Node):
    """A non-keyed term (word or quoted phrase) that searches AniList."""

    text: str


@dataclass
class Not(Node):
    """Negation of a child expression."""

    child: Node
    _ids: set[int] | None = None  # Populated during evaluation


@dataclass
class And(Node):
    """Conjunction (implicit by whitespace)."""

    children: list[Node]


@dataclass
class Or(Node):
    """Disjunction (explicit with `|` or implicit with `~` prefix)."""

    children: list[Node]


@dataclass
class OrMarker(Node):
    """Marker for a term to be included in an OR group within an AND."""

    child: Node


def _make_parser() -> pp.ParserElement:
    identifier = pp.oneOf(
        "anilist id anidb imdb mal tmdb_movie tmdb_show tvdb custom has",
        caseless=True,
    )

    # Normalize identifier to lowercase
    identifier = identifier.setParseAction(lambda _s, _loc, t: str(t[0]).lower())

    integer = pp.Word(pp.nums)
    word = pp.Word(pp.alphanums + "_-.:/@")
    qstring = pp.QuotedString('"', escChar="\\", unquoteResults=True) | pp.QuotedString(
        "'", escChar="\\", unquoteResults=True
    )

    # Tokens for comparisons and ranges
    cmp_op = pp.oneOf("> >= < <=", caseless=False)
    cmp_val = pp.Combine(cmp_op + pp.Word(pp.nums))
    range_val = pp.Combine(pp.Word(pp.nums) + pp.Literal("..") + pp.Word(pp.nums))

    # Normalize value to string
    value = (qstring | range_val | cmp_val | word | integer).setParseAction(
        lambda _s, _loc, toks: str(toks[0])
    )

    colon = pp.Suppress(":")

    # Deserialize key:value into KeyTerm
    key_term = (identifier + colon + value).setParseAction(
        lambda _s, _loc, toks: KeyTerm(key=str(toks[0]), value=str(toks[1]))
    )

    # Normalize bare term to string
    bare = (qstring | word).setParseAction(
        lambda _s, _loc, toks: BareTerm(text=str(toks[0]))
    )

    # Define syntax grammar
    LPAR, RPAR = map(pp.Suppress, "()")
    expr: pp.Forward = pp.Forward()
    not_kw = pp.Keyword("not", caseless=True) | pp.Literal("-")
    tilde = pp.Literal("~")
    pipe = pp.Literal("|")
    atom = key_term | bare | pp.Group(LPAR + expr + RPAR)

    def _prefix_action(_s, _loc, toks):
        """Handle prefix operators.

        Tokens like ['~', '-', atom] or ['-', atom] or ['~', atom] or [atom]
        """
        if not toks:
            return toks
        parts = list(toks)
        node = parts[-1]
        if isinstance(node, list) and len(node) == 1 and isinstance(node[0], Node):
            node = node[0]
        for t in reversed(parts[:-1]):
            if str(t).lower() == "not" or str(t) == "-":
                node = Not(cast(Node, node))
            elif str(t) == "~":
                node = OrMarker(cast(Node, node))
        return node

    pref = (pp.ZeroOrMore(tilde | not_kw) + atom).setParseAction(_prefix_action)

    def _and_action(_s, _loc, toks):
        """Handle conjunction of tokens."""
        required: list[Node] = []
        or_children: list[Node] = []
        for tok in toks:
            cur = tok
            if isinstance(cur, list) and len(cur) == 1 and isinstance(cur[0], Node):
                cur = cur[0]
            if isinstance(cur, OrMarker):
                or_children.append(cur.child)
            else:
                required.append(cast(Node, cur))

        nodes: list[Node] = []
        nodes.extend(required)
        if or_children:
            if len(or_children) == 1:
                nodes.append(or_children[0])
            else:
                nodes.append(Or(or_children))

        if not nodes:
            return And([])
        if len(nodes) == 1:
            return nodes[0]
        return And(nodes)

    conj = pp.OneOrMore(pref).setParseAction(_and_action)

    def _or_action(_s, _loc, toks):
        """Handle disjunction of tokens separated by |."""
        nodes = [tok for tok in toks if tok != "|"]
        flattened = []
        for node in nodes:
            if isinstance(node, list) and len(node) == 1 and isinstance(node[0], Node):
                flattened.append(node[0])
            elif isinstance(node, Node):
                flattened.append(node)
            else:
                flattened.append(node)

        if len(flattened) == 1:
            return flattened[0]
        return Or(flattened)

    # OR has lower precedence than AND (conjunction)
    or_expr = (conj + pp.ZeroOrMore(pp.Suppress(pipe) + conj)).setParseAction(
        _or_action
    )

    expr <<= or_expr
    return expr


PARSER = _make_parser()


def parse_query(q: str) -> Node:
    """Parse the booru-like query string into an AST Node.

    Args:
        q (str): The booru-like query string to parse.

    Returns:
        Node: The root AST node representing the parsed query.

    Raises:
        pyparsing.ParseException on invalid input.
    """
    q = (q or "").strip()
    if not q:
        return And([])

    res = PARSER.parseString(q, parseAll=True)
    node_any = res[0]

    # Normalize single grouped result
    if (
        isinstance(node_any, list)
        and len(node_any) == 1
        and isinstance(node_any[0], Node)
    ):
        return cast(Node, node_any[0])

    if isinstance(node_any, Node):
        return node_any

    # Fallback: try to unwrap one level
    if isinstance(node_any, list) and node_any:
        first = node_any[0]
        if isinstance(first, Node):
            return first

    raise ValueError("Invalid parsed AST for query")


@dataclass
class EvalResult:
    """Evaluation result for a query AST."""

    ids: set[int]
    order_hint: dict[int, int]
    used_bare: bool


def collect_bare_terms(node: Node) -> list[str]:
    """Collect bare term texts from the AST for prefetching.

    Args:
        node (Node): The root AST node.

    Returns:
        list[str]: A list with potential duplicates removed.
    """
    out: list[str] = []

    def _walk(n: Node) -> None:
        """Walk the AST and collect bare terms."""
        if isinstance(n, BareTerm):
            out.append(n.text)
            return
        if isinstance(n, Not):
            _walk(n.child)
            return
        if isinstance(n, (And, Or)):
            for c in n.children:
                _walk(c)
            return

    _walk(node)

    # De-duplicate preserving first occurrence order
    seen: set[str] = set()
    unique: list[str] = []
    for t in out:
        if t not in seen:
            unique.append(t)
            seen.add(t)

    return unique


def evaluate(
    node: Node,
    *,
    db_resolver: DbResolver,
    anilist_resolver: AniListResolver,
    universe_ids: set[int] | None = None,
) -> EvalResult:
    """Evaluate AST into a set of AniList IDs with optional ordering hint.

    Args:
        node (Node): The root AST node to evaluate.
        db_resolver (DbResolver): Function to resolve KeyTerm nodes to AniList IDs.
        anilist_resolver (AniListResolver): Function to resolve BareTerm nodes to
            ordered AniList IDs.
        universe_ids (set[int] | None): Optional set of AniList IDs to use as
            universe for NOT operations. If None, universe is derived from
            all IDs seen in positive terms.

    Returns:
        EvalResult: Evaluation result containing:
            - ids: Set of AniList IDs matching the query.
            - order_hint: Maps AniList ID to rank (lower is earlier) derived from
                BareTerm resolution order.
            - used_bare: True if any BareTerm was used in the query.
    """
    used_bare = False
    order_hint: dict[int, int] = {}

    def eval_node(n: Node) -> set[int]:
        nonlocal used_bare, order_hint
        if isinstance(n, And):
            if not n.children:  # Treated as True
                return set()
            sets = [eval_node(c) for c in n.children]
            if not sets:
                return set()

            base: set[int] | None = None
            for s in sets:
                if base is None:
                    base = set(s)
                else:
                    base &= s
            return base or set()
        if isinstance(n, Or):
            sets = [eval_node(c) for c in n.children]
            out: set[int] = set()
            for s in sets:
                out |= s
            return out
        if isinstance(n, Not):
            # Negation handled by caller using a universe; here evaluate the child
            # and annotate the node with that set.
            child_set = eval_node(n.child)
            # We'll annotate the node with the child set and let caller handle
            # the negation.
            n._ids = child_set
            return set()
        if isinstance(n, KeyTerm):
            return set(db_resolver(n.key, n.value))
        if isinstance(n, BareTerm):
            used_bare = True
            ordered = anilist_resolver(n.text)
            for idx, aid in enumerate(ordered):
                prev = order_hint.get(aid, idx)
                order_hint[aid] = prev if prev <= idx else idx
            return set(ordered)
        return set()

    ids = eval_node(node)

    def collect_nodes(n: Node, lst: list[Node]):
        lst.append(n)
        if isinstance(n, (And, Or)):
            for c in n.children:
                collect_nodes(c, lst)

    nodes: list[Node] = []
    collect_nodes(node, nodes)
    neg_sets: list[set[int]] = []
    for n in nodes:
        if isinstance(n, Not) and n._ids is not None:
            neg_sets.append(n._ids)

    # Build a universe: caller-provided IDs (when available), unioned with
    # positive sources we have in order_hint keys and ids
    universe: set[int] = set(universe_ids or set()) | set(ids) | set(order_hint.keys())
    for s in neg_sets:
        universe |= set(s)

    # Apply negations: subtract union of neg_sets. If the expression is purely
    # negative (no positive ids), expand to the provided universe to allow
    # subtraction; otherwise, keep empty results empty.
    neg_union: set[int] = set()
    for s in neg_sets:
        neg_union |= s
    if not ids and neg_union and universe:
        ids = set(universe)
    if neg_union:
        ids -= neg_union

    return EvalResult(ids=ids, order_hint=order_hint, used_bare=used_bare)
