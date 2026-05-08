"""Search-domain contracts layered on Evidpath's ranked-list runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

from ...schema import (
    AgentState,
    Observation,
    RankedItem,
    RankedList,
    ScenarioConfig,
)

Scalar = str | int | float | bool


@dataclass(frozen=True)
class SearchRequest:
    """Canonical request sent to a search ranker under audit."""

    request_id: str
    query: str
    user_id: str = ""
    session_id: str = ""
    user_context: Mapping[str, Scalar | tuple[str, ...]] = field(default_factory=dict)
    locale: str = ""
    freshness_window_days: int | None = None
    max_results: int = 10


@dataclass(frozen=True)
class SearchResult:
    """Canonical ranked search result."""

    result_id: str
    title: str
    snippet: str
    url: str
    result_type: str
    relevance_score: float
    rank: int
    freshness_timestamp: str = ""
    freshness_score: float = 0.0


@dataclass(frozen=True)
class SearchResponse:
    """Canonical response returned by a search ranker under audit."""

    request_id: str
    results: tuple[SearchResult, ...]


def build_search_request(
    agent_state: AgentState,
    observation: Observation,
    scenario_config: ScenarioConfig,
) -> SearchRequest:
    """Build a search request from the shared rollout runtime state."""
    context = observation.scenario_context
    query = (
        context.context_hint
        or scenario_config.context_hint
        or scenario_config.test_goal
        or context.description
        or scenario_config.description
        or context.scenario_name
        or scenario_config.name
    )
    return SearchRequest(
        request_id=f"{agent_state.agent_id}-{context.scenario_id or context.scenario_name}-{observation.step_index}",
        query=query,
        user_id=agent_state.agent_id,
        session_id=observation.session_id,
        user_context={
            "archetype_label": agent_state.archetype_label,
            "preferred_genres": agent_state.preferred_genres,
            "history_item_ids": agent_state.history_item_ids,
            "clicked_item_ids": agent_state.clicked_item_ids,
        },
        max_results=10,
    )


def request_to_payload(request: SearchRequest) -> dict[str, object]:
    """Convert a search request to JSON-serializable payload values."""
    return asdict(request)


def response_to_ranked_list(
    response: SearchResponse,
    *,
    ranked_list_id: str,
    step_index: int,
) -> RankedList:
    """Normalize a search response into the shared ranked-list container."""
    return RankedList(
        slate_id=ranked_list_id,
        step_index=step_index,
        items=tuple(_result_to_ranked_item(result) for result in response.results),
    )


def _result_to_ranked_item(result: SearchResult) -> RankedItem:
    return RankedItem(
        item_id=result.result_id,
        title=result.title,
        genre="",
        score=result.relevance_score,
        rank=result.rank,
        popularity=0.0,
        novelty=0.0,
        item_type=result.result_type,
        metadata={
            "snippet": result.snippet,
            "url": result.url,
            "freshness_timestamp": result.freshness_timestamp,
            "freshness_score": result.freshness_score,
        },
    )


def ranked_list_id(
    agent_state: AgentState,
    observation: Observation,
    scenario_config: ScenarioConfig,
) -> str:
    """Return the stable ranked-list id used by search drivers."""
    return (
        f"{scenario_config.scenario_id or scenario_config.name}-"
        f"{agent_state.agent_id}-{observation.step_index}"
    )
