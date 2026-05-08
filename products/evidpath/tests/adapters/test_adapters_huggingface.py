"""Unit tests for the Hugging Face adapter using a stub pipeline."""

from __future__ import annotations

import sys

import pytest


class _StubPipeline:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def __call__(self, prompt):
        self.calls.append(prompt)
        return list(self._payload)


def test_wrap_pipeline_maps_default_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "transformers", object())
    from evidpath.adapters.huggingface import wrap_pipeline

    pipeline = _StubPipeline(
        [
            {"item_id": "m1", "score": 0.9},
            {"item_id": "m2", "score": 0.5},
        ]
    )
    fn = wrap_pipeline(pipeline)
    response = fn(_make_request())
    assert [item.item_id for item in response.items] == ["m1", "m2"]
    assert response.items[0].score == pytest.approx(0.9)


def test_wrap_pipeline_respects_custom_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "transformers", object())
    from evidpath.adapters.huggingface import wrap_pipeline

    pipeline = _StubPipeline(
        [
            {"movie": "x", "rating": 0.7},
        ]
    )
    fn = wrap_pipeline(pipeline, item_key="movie", score_key="rating")
    response = fn(_make_request())
    assert response.items[0].item_id == "x"
    assert response.items[0].score == pytest.approx(0.7)


def test_wrap_pipeline_raises_friendly_error_when_extra_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "transformers", raising=False)
    monkeypatch.delitem(sys.modules, "evidpath.adapters.huggingface", raising=False)
    with pytest.raises(ImportError, match="evidpath\\[huggingface\\]"):
        import evidpath.adapters.huggingface  # noqa: F401


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
