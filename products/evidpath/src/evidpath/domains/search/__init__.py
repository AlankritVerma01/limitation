"""Search domain contracts and reference utilities."""

from .contracts import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    request_to_payload,
    response_to_ranked_list,
)
from .definition import build_search_domain_definition
from .judge import SearchJudge
from .policy import SearchAgentPolicy, build_seeded_search_archetypes
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
    "SearchAgentPolicy",
    "build_scenarios",
    "build_search_domain_definition",
    "build_seeded_search_archetypes",
    "request_to_payload",
    "response_to_ranked_list",
    "resolve_built_in_search_scenarios",
    "search",
)
