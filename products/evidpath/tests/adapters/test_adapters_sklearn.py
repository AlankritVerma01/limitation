"""Unit tests for the sklearn classifier adapter using a stub estimator."""

from __future__ import annotations

import sys

import pytest


class _StubClassifier:
    def __init__(self, scores_by_item):
        self._scores = scores_by_item
        self.calls = []

    def predict_proba(self, features):
        self.calls.append(features)
        item_id = features.get("item_id")
        score = self._scores.get(item_id, 0.0)
        return [[1.0 - score, score]]


def test_wrap_classifier_ranks_catalog_by_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "sklearn", object())
    from evidpath.adapters.sklearn import wrap_classifier

    estimator = _StubClassifier({"x": 0.8, "y": 0.4, "z": 0.9})
    fn = wrap_classifier(estimator, catalog=("x", "y", "z"), top_k=2)
    response = fn(_make_request())
    assert [item.item_id for item in response.items] == ["z", "x"]
    assert response.items[0].score == pytest.approx(0.9)


def test_wrap_classifier_raises_friendly_error_when_extra_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "sklearn", raising=False)
    monkeypatch.delitem(sys.modules, "evidpath.adapters.sklearn", raising=False)
    with pytest.raises(ImportError, match="evidpath\\[sklearn\\]"):
        import evidpath.adapters.sklearn  # noqa: F401


def _make_request():
    from evidpath import AdapterRequest

    return AdapterRequest(
        request_id="r1",
        agent_id="u1",
        scenario_name="s",
        scenario_profile="p",
        step_index=0,
        history_depth=0,
        history_item_ids=("a",),
        recent_exposure_ids=(),
        preferred_genres=(),
    )
