"""Tests for the deterministic reference search backend."""

from __future__ import annotations

from evidpath.domains.search import SearchRequest
from evidpath.domains.search.reference_backend import ReferenceSearchBackend


def test_reference_search_is_deterministic() -> None:
    backend = ReferenceSearchBackend.from_artifacts()
    request = SearchRequest(
        request_id="req-1",
        query="current weather alerts toronto",
        freshness_window_days=2,
        max_results=3,
    )

    first = backend.predict(request)
    second = backend.predict(request)

    assert first == second
    assert first.results[0].result_id == "doc-weather-alerts"
    assert first.results[0].freshness_score == 0.97


def test_reference_search_returns_zero_results_for_unmatched_query() -> None:
    backend = ReferenceSearchBackend.from_artifacts()
    response = backend.predict(SearchRequest(request_id="req-2", query="zzzz qqqq"))

    assert response.results == ()
