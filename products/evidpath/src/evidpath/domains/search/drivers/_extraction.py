"""Dot-path response extraction for the search schema-mapped driver."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..contracts import SearchResult


class SearchResponseExtractionError(RuntimeError):
    """Raised when a configured path cannot be resolved."""


def resolve_dot_path(payload: Any, dot_path: str) -> Any:
    if dot_path == ".":
        return payload
    cursor: Any = payload
    walked: list[str] = []
    for segment in dot_path.split("."):
        walked.append(segment)
        path_so_far = ".".join(walked)
        if isinstance(cursor, Mapping):
            if segment not in cursor:
                raise SearchResponseExtractionError(
                    f"Dot-path `{dot_path}` missing segment `{path_so_far}`."
                )
            cursor = cursor[segment]
        elif isinstance(cursor, list):
            try:
                index = int(segment)
            except ValueError:
                raise SearchResponseExtractionError(
                    f"Dot-path `{dot_path}` segment `{path_so_far}` is not an integer index."
                ) from None
            if index >= len(cursor) or index < -len(cursor):
                raise SearchResponseExtractionError(
                    f"Dot-path `{dot_path}` segment `{path_so_far}` is out of range."
                )
            cursor = cursor[index]
        else:
            raise SearchResponseExtractionError(
                f"Dot-path `{dot_path}` cannot descend into a scalar at `{path_so_far}`."
            )
    return cursor


def extract_results(payload: Any, mapping) -> tuple[SearchResult, ...]:
    results_payload = (
        resolve_dot_path(payload, mapping.results_path)
        if mapping.results_path
        else payload
    )
    if not isinstance(results_payload, list):
        raise SearchResponseExtractionError(
            f"Results path `{mapping.results_path or '.'}` resolved to {type(results_payload).__name__}, not a list."
        )
    results: list[SearchResult] = []
    for index, raw_result in enumerate(results_payload):
        result_id = _extract_field(raw_result, mapping.result_id_field, label="result_id")
        title = _extract_field(raw_result, mapping.title_field, label="title")
        snippet = _extract_field(raw_result, mapping.snippet_field, label="snippet")
        url = _extract_field(raw_result, mapping.url_field, label="url")
        result_type = _extract_field(raw_result, mapping.type_field, label="result_type")
        score = _extract_field(
            raw_result,
            mapping.relevance_score_field,
            label="relevance_score",
        )
        freshness_timestamp = (
            _extract_field(
                raw_result,
                mapping.freshness_timestamp_field,
                label="freshness_timestamp",
            )
            if mapping.freshness_timestamp_field
            else ""
        )
        freshness_score = (
            _extract_field(
                raw_result,
                mapping.freshness_score_field,
                label="freshness_score",
            )
            if mapping.freshness_score_field
            else 0.0
        )
        results.append(
            SearchResult(
                result_id=str(result_id),
                title=str(title),
                snippet=str(snippet),
                url=str(url),
                result_type=str(result_type),
                relevance_score=float(score),
                rank=index + 1,
                freshness_timestamp=str(freshness_timestamp),
                freshness_score=float(freshness_score),
            )
        )
    return tuple(results)


def _extract_field(raw_item: Any, dot_path: str, *, label: str) -> Any:
    try:
        return resolve_dot_path(raw_item, dot_path)
    except SearchResponseExtractionError as exc:
        raise SearchResponseExtractionError(
            f"Could not extract `{label}` via dot-path `{dot_path}`: {exc}"
        ) from exc
