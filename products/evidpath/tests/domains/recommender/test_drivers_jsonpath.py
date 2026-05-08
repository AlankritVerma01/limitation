"""Tests for the JSONPath subset parser and evaluator."""

from __future__ import annotations

import pytest
from evidpath.domains.recommender.drivers._jsonpath import (
    ChildSegment,
    EqualityFilterSegment,
    IndexSegment,
    JsonPathEvalError,
    JsonPathExpression,
    JsonPathParseError,
    Token,
    TokenKind,
    WildcardSegment,
    evaluate,
    parse_jsonpath,
    tokenize,
)


def test_tokenize_root_only() -> None:
    assert tokenize("$") == [Token(kind=TokenKind.ROOT, value="$")]


def test_tokenize_root_with_child() -> None:
    tokens = tokenize("$.results.rankings")
    assert tokens == [
        Token(kind=TokenKind.ROOT, value="$"),
        Token(kind=TokenKind.DOT, value="."),
        Token(kind=TokenKind.NAME, value="results"),
        Token(kind=TokenKind.DOT, value="."),
        Token(kind=TokenKind.NAME, value="rankings"),
    ]


def test_tokenize_index_and_wildcard() -> None:
    tokens = tokenize("$.items[0]")
    assert [tok.kind for tok in tokens] == [
        TokenKind.ROOT,
        TokenKind.DOT,
        TokenKind.NAME,
        TokenKind.LBRACKET,
        TokenKind.INTEGER,
        TokenKind.RBRACKET,
    ]
    tokens = tokenize("$.items[-3]")
    int_token = next(tok for tok in tokens if tok.kind == TokenKind.INTEGER)
    assert int_token.value == "-3"
    tokens = tokenize("$.buckets[*]")
    kinds = [tok.kind for tok in tokens]
    assert TokenKind.STAR in kinds


def test_tokenize_filter_string_literal() -> None:
    tokens = tokenize("$.buckets[?(@.name=='main')]")
    kinds = [tok.kind for tok in tokens]
    assert TokenKind.FILTER_OPEN in kinds
    assert TokenKind.AT in kinds
    assert TokenKind.EQ in kinds
    assert TokenKind.STRING in kinds
    string_token = next(tok for tok in tokens if tok.kind == TokenKind.STRING)
    assert string_token.value == "main"


def test_tokenize_filter_numeric_literal() -> None:
    tokens = tokenize("$.items[?(@.id==42)]")
    int_token = next(tok for tok in tokens if tok.kind == TokenKind.INTEGER)
    assert int_token.value == "42"


def test_tokenize_rejects_unknown_character() -> None:
    with pytest.raises(JsonPathParseError, match="Unexpected character"):
        tokenize("$.foo#bar")


def test_tokenize_rejects_unterminated_string() -> None:
    with pytest.raises(JsonPathParseError, match="Unterminated string"):
        tokenize("$.foo[?(@.name=='main")


def test_parse_root_only() -> None:
    assert parse_jsonpath("$") == JsonPathExpression(segments=())


def test_parse_chain() -> None:
    expr = parse_jsonpath("$.results.rankings")
    assert expr.segments == (ChildSegment("results"), ChildSegment("rankings"))


def test_parse_index_and_wildcard() -> None:
    expr = parse_jsonpath("$.items[0].name")
    assert expr.segments == (
        ChildSegment("items"),
        IndexSegment(0),
        ChildSegment("name"),
    )
    expr = parse_jsonpath("$.items[-1]")
    assert expr.segments == (ChildSegment("items"), IndexSegment(-1))
    expr = parse_jsonpath("$.buckets[*].items[*]")
    assert expr.segments == (
        ChildSegment("buckets"),
        WildcardSegment(),
        ChildSegment("items"),
        WildcardSegment(),
    )


def test_parse_string_filter() -> None:
    expr = parse_jsonpath("$.buckets[?(@.name=='main')].items[*]")
    assert expr.segments == (
        ChildSegment("buckets"),
        EqualityFilterSegment(field="name", literal="main"),
        ChildSegment("items"),
        WildcardSegment(),
    )


def test_parse_numeric_filter() -> None:
    expr = parse_jsonpath("$.items[?(@.priority==1)]")
    assert expr.segments == (
        ChildSegment("items"),
        EqualityFilterSegment(field="priority", literal=1),
    )


def test_parse_rejects_missing_root() -> None:
    with pytest.raises(JsonPathParseError, match="must start with `\\$`"):
        parse_jsonpath(".items")


def test_parse_rejects_trailing_dot() -> None:
    with pytest.raises(JsonPathParseError, match="Expected NAME after DOT"):
        parse_jsonpath("$.results.")


def test_parse_rejects_unsupported_filter_operator() -> None:
    with pytest.raises(JsonPathParseError, match="Expected `==`"):
        parse_jsonpath("$.items[?(@.name!='x')]")


def test_evaluate_root_returns_payload() -> None:
    expr = parse_jsonpath("$")
    assert evaluate(expr, {"a": 1}) == [{"a": 1}]


def test_evaluate_child_chain() -> None:
    payload = {"results": {"rankings": [1, 2, 3]}}
    expr = parse_jsonpath("$.results.rankings")
    assert evaluate(expr, payload) == [[1, 2, 3]]


def test_evaluate_index_positive_and_negative() -> None:
    payload = {"items": ["a", "b", "c"]}
    assert evaluate(parse_jsonpath("$.items[0]"), payload) == ["a"]
    assert evaluate(parse_jsonpath("$.items[-1]"), payload) == ["c"]


def test_evaluate_wildcard_array() -> None:
    payload = {"items": [{"id": 1}, {"id": 2}]}
    assert evaluate(parse_jsonpath("$.items[*]"), payload) == [{"id": 1}, {"id": 2}]


def test_evaluate_wildcard_object_collects_values() -> None:
    payload = {"map": {"a": 1, "b": 2}}
    result = evaluate(parse_jsonpath("$.map[*]"), payload)
    assert sorted(result) == [1, 2]


def test_evaluate_equality_filter_string() -> None:
    payload = {
        "buckets": [
            {"name": "main", "items": [{"id": "x"}]},
            {"name": "fallback", "items": [{"id": "y"}]},
        ]
    }
    expr = parse_jsonpath("$.buckets[?(@.name=='main')].items[*]")
    assert evaluate(expr, payload) == [{"id": "x"}]


def test_evaluate_equality_filter_numeric() -> None:
    payload = {"items": [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]}
    expr = parse_jsonpath("$.items[?(@.id==2)]")
    assert evaluate(expr, payload) == [{"id": 2, "v": "b"}]


def test_evaluate_missing_child_raises() -> None:
    expr = parse_jsonpath("$.results.rankings")
    with pytest.raises(JsonPathEvalError, match="rankings"):
        evaluate(expr, {"results": {}})


def test_evaluate_index_out_of_range_raises() -> None:
    expr = parse_jsonpath("$.items[5]")
    with pytest.raises(JsonPathEvalError, match="out of range"):
        evaluate(expr, {"items": ["a"]})


def test_evaluate_wildcard_on_scalar_raises() -> None:
    expr = parse_jsonpath("$.x[*]")
    with pytest.raises(JsonPathEvalError, match="wildcard"):
        evaluate(expr, {"x": 42})
