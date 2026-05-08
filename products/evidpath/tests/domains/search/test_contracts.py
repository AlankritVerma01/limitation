"""Tests for search-domain contracts."""

from __future__ import annotations

from evidpath.domains.search import (
    SearchResponse,
    SearchResult,
    response_to_ranked_list,
)


def test_search_response_converts_to_ranked_list() -> None:
    response = SearchResponse(
        request_id="req-1",
        results=(
            SearchResult(
                result_id="r1",
                title="Live Weather Alerts",
                snippet="Current warnings.",
                url="https://example.com/weather",
                result_type="news",
                relevance_score=0.95,
                rank=1,
                freshness_timestamp="2026-05-06T16:30:00Z",
                freshness_score=0.97,
            ),
        ),
    )

    ranked_list = response_to_ranked_list(
        response,
        ranked_list_id="scenario-agent-0",
        step_index=0,
    )

    assert ranked_list.ranked_list_id == "scenario-agent-0"
    assert ranked_list.items[0].item_id == "r1"
    assert ranked_list.items[0].item_type == "news"
    assert ranked_list.items[0].metadata["snippet"] == "Current warnings."
