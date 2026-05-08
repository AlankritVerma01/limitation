"""JSONPath subset for recommender response extraction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class JsonPathParseError(RuntimeError):
    """Raised when a JSONPath expression cannot be tokenized or parsed."""


class JsonPathEvalError(RuntimeError):
    """Raised when a parsed JSONPath expression cannot be evaluated."""


class TokenKind(Enum):
    ROOT = "ROOT"
    DOT = "DOT"
    NAME = "NAME"
    LBRACKET = "LBRACKET"
    RBRACKET = "RBRACKET"
    INTEGER = "INTEGER"
    STAR = "STAR"
    FILTER_OPEN = "FILTER_OPEN"
    FILTER_CLOSE = "FILTER_CLOSE"
    AT = "AT"
    EQ = "EQ"
    STRING = "STRING"


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    value: str


def tokenize(expression: str) -> list[Token]:
    """Tokenize a JSONPath expression into a flat token list."""
    tokens: list[Token] = []
    i = 0
    n = len(expression)
    while i < n:
        ch = expression[i]
        if ch == "$":
            tokens.append(Token(TokenKind.ROOT, "$"))
            i += 1
        elif ch == ".":
            tokens.append(Token(TokenKind.DOT, "."))
            i += 1
        elif ch == "[":
            if expression[i : i + 3] == "[?(":
                tokens.append(Token(TokenKind.FILTER_OPEN, "[?("))
                i += 3
            else:
                tokens.append(Token(TokenKind.LBRACKET, "["))
                i += 1
        elif ch == "]":
            tokens.append(Token(TokenKind.RBRACKET, "]"))
            i += 1
        elif ch == ")" and expression[i : i + 2] == ")]":
            tokens.append(Token(TokenKind.FILTER_CLOSE, ")]"))
            i += 2
        elif ch == "*":
            tokens.append(Token(TokenKind.STAR, "*"))
            i += 1
        elif ch == "@":
            tokens.append(Token(TokenKind.AT, "@"))
            i += 1
        elif expression[i : i + 2] == "==":
            tokens.append(Token(TokenKind.EQ, "=="))
            i += 2
        elif ch == "!":
            raise JsonPathParseError(f"Expected `==` in filter in `{expression}`.")
        elif ch == "'":
            end = expression.find("'", i + 1)
            if end == -1:
                raise JsonPathParseError(
                    f"Unterminated string literal at offset {i} in `{expression}`."
                )
            tokens.append(Token(TokenKind.STRING, expression[i + 1 : end]))
            i = end + 1
        elif ch == "-" or ch.isdigit():
            j = i + 1
            while j < n and expression[j].isdigit():
                j += 1
            literal = expression[i:j]
            if literal == "-" or not any(c.isdigit() for c in literal):
                raise JsonPathParseError(
                    f"Unexpected character `-` at offset {i} in `{expression}`."
                )
            tokens.append(Token(TokenKind.INTEGER, literal))
            i = j
        elif ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (expression[j].isalnum() or expression[j] == "_"):
                j += 1
            tokens.append(Token(TokenKind.NAME, expression[i:j]))
            i = j
        else:
            raise JsonPathParseError(
                f"Unexpected character `{ch}` at offset {i} in `{expression}`."
            )
    return tokens


@dataclass(frozen=True)
class ChildSegment:
    name: str


@dataclass(frozen=True)
class IndexSegment:
    index: int


@dataclass(frozen=True)
class WildcardSegment:
    pass


@dataclass(frozen=True)
class EqualityFilterSegment:
    field: str
    literal: str | int


Segment = ChildSegment | IndexSegment | WildcardSegment | EqualityFilterSegment


@dataclass(frozen=True)
class JsonPathExpression:
    segments: tuple[Segment, ...]


def parse_jsonpath(expression: str) -> JsonPathExpression:
    """Parse a JSONPath expression into a typed segment chain."""
    tokens = tokenize(expression)
    if not tokens or tokens[0].kind is not TokenKind.ROOT:
        raise JsonPathParseError(f"JSONPath `{expression}` must start with `$`.")
    segments: list[Segment] = []
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token.kind is TokenKind.DOT:
            if i + 1 >= len(tokens) or tokens[i + 1].kind is not TokenKind.NAME:
                raise JsonPathParseError(f"Expected NAME after DOT in `{expression}`.")
            segments.append(ChildSegment(tokens[i + 1].value))
            i += 2
        elif token.kind is TokenKind.LBRACKET:
            inner = tokens[i + 1] if i + 1 < len(tokens) else None
            close = tokens[i + 2] if i + 2 < len(tokens) else None
            if inner is None or close is None or close.kind is not TokenKind.RBRACKET:
                raise JsonPathParseError(f"Unclosed bracket segment in `{expression}`.")
            if inner.kind is TokenKind.INTEGER:
                segments.append(IndexSegment(int(inner.value)))
            elif inner.kind is TokenKind.STAR:
                segments.append(WildcardSegment())
            else:
                raise JsonPathParseError(
                    f"Unsupported bracket segment in `{expression}`."
                )
            i += 3
        elif token.kind is TokenKind.FILTER_OPEN:
            expected = [
                TokenKind.AT,
                TokenKind.DOT,
                TokenKind.NAME,
                TokenKind.EQ,
            ]
            for offset, kind in enumerate(expected, start=1):
                if i + offset >= len(tokens) or tokens[i + offset].kind is not kind:
                    if kind is TokenKind.EQ:
                        raise JsonPathParseError(
                            f"Expected `==` in filter in `{expression}`."
                        )
                    raise JsonPathParseError(f"Malformed filter in `{expression}`.")
            field_token = tokens[i + 3]
            literal_token = tokens[i + 5] if i + 5 < len(tokens) else None
            close_token = tokens[i + 6] if i + 6 < len(tokens) else None
            if (
                literal_token is None
                or close_token is None
                or close_token.kind is not TokenKind.FILTER_CLOSE
            ):
                raise JsonPathParseError(f"Unterminated filter in `{expression}`.")
            if literal_token.kind is TokenKind.STRING:
                literal: str | int = literal_token.value
            elif literal_token.kind is TokenKind.INTEGER:
                literal = int(literal_token.value)
            else:
                raise JsonPathParseError(
                    f"Filter literal must be a string or integer in `{expression}`."
                )
            segments.append(
                EqualityFilterSegment(field=field_token.value, literal=literal)
            )
            i += 7
        else:
            raise JsonPathParseError(
                f"Unexpected token `{token.value}` in `{expression}`."
            )
    return JsonPathExpression(segments=tuple(segments))


def evaluate(expression: JsonPathExpression, payload: Any) -> list[Any]:
    """Evaluate a parsed JSONPath expression against a JSON-like payload."""
    cursor: list[Any] = [payload]
    for segment in expression.segments:
        cursor = _apply_segment(segment, cursor)
    return cursor


def _apply_segment(segment: Segment, cursor: list[Any]) -> list[Any]:
    out: list[Any] = []
    if isinstance(segment, ChildSegment):
        for item in cursor:
            if not isinstance(item, dict):
                raise JsonPathEvalError(
                    f"Cannot read child `{segment.name}` from non-object value."
                )
            if segment.name not in item:
                raise JsonPathEvalError(f"Missing child `{segment.name}`.")
            out.append(item[segment.name])
        return out
    if isinstance(segment, IndexSegment):
        for item in cursor:
            if not isinstance(item, list):
                raise JsonPathEvalError(
                    f"Cannot index into non-array value at index `{segment.index}`."
                )
            idx = segment.index
            if idx < 0:
                idx = len(item) + idx
            if idx < 0 or idx >= len(item):
                raise JsonPathEvalError(f"Index `{segment.index}` is out of range.")
            out.append(item[idx])
        return out
    if isinstance(segment, WildcardSegment):
        for item in cursor:
            if isinstance(item, list):
                out.extend(item)
            elif isinstance(item, dict):
                out.extend(item.values())
            else:
                raise JsonPathEvalError("Cannot apply wildcard to scalar value.")
        return out
    if isinstance(segment, EqualityFilterSegment):
        for item in cursor:
            if not isinstance(item, list):
                raise JsonPathEvalError("Cannot apply filter to non-array value.")
            for candidate in item:
                if not isinstance(candidate, dict):
                    raise JsonPathEvalError("Cannot apply filter to non-object item.")
                if candidate.get(segment.field) == segment.literal:
                    out.append(candidate)
        return out
    raise JsonPathEvalError(f"Unsupported JSONPath segment `{segment}`.")
