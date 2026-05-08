"""MLflow pyfunc adapter for in-process recommender audits."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import mlflow  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "evidpath.adapters.mlflow requires `pip install evidpath[mlflow]`."
    ) from exc

from ..schema import AdapterRequest, AdapterResponse, SlateItem


def wrap_pyfunc(
    model: Any,
    *,
    item_key: str = "item_id",
    score_key: str = "score",
) -> Callable[[AdapterRequest], AdapterResponse]:
    """Wrap an MLflow pyfunc model into an evidpath callable."""

    def call(adapter_request: AdapterRequest) -> AdapterResponse:
        df = _request_to_dataframe(adapter_request)
        raw = list(model.predict(df))
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


def _request_to_dataframe(adapter_request: AdapterRequest):
    """Encode an AdapterRequest as a single-row pandas DataFrame."""
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "agent_id": adapter_request.agent_id,
                "scenario_name": adapter_request.scenario_name,
                "history_item_ids": list(adapter_request.history_item_ids),
                "step_index": adapter_request.step_index,
            }
        ]
    )
