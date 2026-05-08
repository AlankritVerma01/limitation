"""Hugging Face Pipeline adapter for in-process recommender audits."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import transformers  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "evidpath.adapters.huggingface requires `pip install evidpath[huggingface]`."
    ) from exc

from ..schema import AdapterRequest, AdapterResponse, SlateItem


def wrap_pipeline(
    pipeline: Callable[[str], Any],
    *,
    item_key: str = "item_id",
    score_key: str = "score",
) -> Callable[[AdapterRequest], AdapterResponse]:
    """Wrap a Hugging Face Pipeline into an evidpath callable."""

    def call(adapter_request: AdapterRequest) -> AdapterResponse:
        prompt = " ".join(adapter_request.history_item_ids) or adapter_request.agent_id
        raw = list(pipeline(prompt))
        items = tuple(
            SlateItem(
                item_id=str(entry[item_key]),
                title=str(entry.get("title", "")),
                genre=str(entry.get("genre", "")),
                score=float(entry[score_key]),
                rank=index + 1,
                popularity=float(entry.get("popularity", 0.0)),
                novelty=float(entry.get("novelty", 0.0)),
            )
            for index, entry in enumerate(raw)
        )
        return AdapterResponse(request_id=adapter_request.request_id, items=items)

    return call
