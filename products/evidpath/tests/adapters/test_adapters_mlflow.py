"""Unit tests for the MLflow pyfunc adapter using a stub model."""

from __future__ import annotations

import sys

import pytest


class _StubMlflowModel:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def predict(self, df):
        self.calls.append(df)
        return list(self._rows)


def test_wrap_pyfunc_maps_default_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "mlflow", object())
    monkeypatch.setitem(sys.modules, "pandas", object())
    import evidpath.adapters.mlflow as mod

    monkeypatch.setattr(mod, "_request_to_dataframe", lambda req: {"agent_id": req.agent_id})

    model = _StubMlflowModel(
        [
            {"item_id": "m1", "score": 0.8},
            {"item_id": "m2", "score": 0.6},
        ]
    )
    fn = mod.wrap_pyfunc(model)
    response = fn(_make_request())
    assert [item.item_id for item in response.items] == ["m1", "m2"]


def test_wrap_pyfunc_raises_friendly_error_when_extra_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "mlflow", raising=False)
    monkeypatch.delitem(sys.modules, "evidpath.adapters.mlflow", raising=False)
    with pytest.raises(ImportError, match="evidpath\\[mlflow\\]"):
        import evidpath.adapters.mlflow  # noqa: F401


def _make_request():
    from evidpath import AdapterRequest

    return AdapterRequest(
        request_id="r1",
        agent_id="u1",
        scenario_name="s",
        scenario_profile="p",
        step_index=0,
        history_depth=0,
        history_item_ids=("a", "b"),
        recent_exposure_ids=(),
        preferred_genres=(),
    )
