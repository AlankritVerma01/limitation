"""Dot-path response extraction for the schema-mapped recommender driver."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ....schema import SlateItem


class ResponseExtractionError(RuntimeError):
    """Raised when a configured dot-path cannot be resolved."""


def resolve_dot_path(payload: Any, dot_path: str) -> Any:
    """Walk a JSON-like payload along dot-path segments."""
    if dot_path == ".":
        return payload
    cursor: Any = payload
    walked: list[str] = []
    for segment in dot_path.split("."):
        walked.append(segment)
        path_so_far = ".".join(walked)
        if isinstance(cursor, Mapping):
            if segment not in cursor:
                raise ResponseExtractionError(
                    f"Dot-path `{dot_path}` missing segment `{path_so_far}`."
                )
            cursor = cursor[segment]
        elif isinstance(cursor, list):
            try:
                index = int(segment)
            except ValueError:
                raise ResponseExtractionError(
                    f"Dot-path `{dot_path}` segment `{path_so_far}` is not an integer index."
                ) from None
            if index >= len(cursor) or index < -len(cursor):
                raise ResponseExtractionError(
                    f"Dot-path `{dot_path}` segment `{path_so_far}` is out of range."
                )
            cursor = cursor[index]
        else:
            raise ResponseExtractionError(
                f"Dot-path `{dot_path}` cannot descend into a scalar at `{path_so_far}`."
            )
    return cursor


def extract_items(payload: Any, mapping) -> tuple[SlateItem, ...]:
    """Resolve a response payload into slate items."""
    items_payload = resolve_dot_path(payload, mapping.items_path) if mapping.items_path else payload
    if not isinstance(items_payload, list):
        raise ResponseExtractionError(
            f"Items path `{mapping.items_path or '.'}` resolved to {type(items_payload).__name__}, not a list."
        )
    items: list[SlateItem] = []
    for index, raw_item in enumerate(items_payload):
        item_id = _extract_field(raw_item, mapping.item_id_field, label="item_id")
        score = _extract_field(raw_item, mapping.score_field, label="score")
        title = (
            _extract_field(raw_item, mapping.title_field, label="title")
            if mapping.title_field
            else ""
        )
        items.append(
            SlateItem(
                item_id=str(item_id),
                title=str(title) if title is not None else "",
                genre="",
                score=float(score),
                rank=index + 1,
                popularity=0.0,
                novelty=0.0,
            )
        )
    return tuple(items)


def _extract_field(raw_item: Any, dot_path: str, *, label: str) -> Any:
    try:
        return resolve_dot_path(raw_item, dot_path)
    except ResponseExtractionError as exc:
        raise ResponseExtractionError(
            f"Could not extract `{label}` via dot-path `{dot_path}`: {exc}"
        ) from exc
