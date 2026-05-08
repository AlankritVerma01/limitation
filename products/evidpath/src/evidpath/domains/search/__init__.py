"""Search domain contracts and reference utilities."""

from .contracts import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    request_to_payload,
    response_to_ranked_list,
)
from .judge import SearchJudge
from .reference_backend import ReferenceSearchBackend, search
from .scenarios import (
    BUILT_IN_SEARCH_SCENARIO_NAMES,
    BUILT_IN_SEARCH_SCENARIOS,
    SearchScenario,
    build_scenarios,
    resolve_built_in_search_scenarios,
)

__all__ = (
    "BUILT_IN_SEARCH_SCENARIO_NAMES",
    "BUILT_IN_SEARCH_SCENARIOS",
    "ReferenceSearchBackend",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "SearchJudge",
    "SearchScenario",
    "build_scenarios",
    "request_to_payload",
    "response_to_ranked_list",
    "resolve_built_in_search_scenarios",
    "search",
)
