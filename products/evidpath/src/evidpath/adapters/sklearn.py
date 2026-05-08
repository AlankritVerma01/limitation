"""scikit-learn classifier adapter for in-process recommender audits."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import sklearn  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "evidpath.adapters.sklearn requires `pip install evidpath[sklearn]`."
    ) from exc

from ..schema import AdapterRequest, AdapterResponse, SlateItem


def wrap_classifier(
    estimator: Any,
    *,
    catalog: tuple[str, ...],
    score_method: str = "predict_proba",
    top_k: int = 5,
) -> Callable[[AdapterRequest], AdapterResponse]:
    """Wrap a sklearn classifier-style estimator into an evidpath callable."""
    score_fn = getattr(estimator, score_method, None)
    if not callable(score_fn):
        raise TypeError(f"Estimator does not implement `{score_method}(features)`.")

    def call(adapter_request: AdapterRequest) -> AdapterResponse:
        scored: list[tuple[str, float]] = []
        for item_id in catalog:
            features = _build_features(adapter_request, item_id)
            probas = score_fn(features)
            score = float(_extract_positive_class(probas))
            scored.append((item_id, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        items = tuple(
            SlateItem(
                item_id=item_id,
                title="",
                genre="",
                score=score,
                rank=index + 1,
                popularity=0.0,
                novelty=0.0,
            )
            for index, (item_id, score) in enumerate(scored[:top_k])
        )
        return AdapterResponse(request_id=adapter_request.request_id, items=items)

    return call


def _build_features(adapter_request: AdapterRequest, item_id: str) -> dict[str, object]:
    return {
        "agent_id": adapter_request.agent_id,
        "item_id": item_id,
        "history_depth": adapter_request.history_depth,
    }


def _extract_positive_class(probas: Any) -> float:
    """Pull the positive-class probability out of a single-row proba matrix."""
    row = probas[0]
    if len(row) >= 2:
        return row[-1]
    return row[0]
