"""Tests for the in-process search driver."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest
from evidpath.domains.search import SearchResponse, SearchResult
from evidpath.domains.search.drivers import (
    InProcessSearchDriver,
    InProcessSearchDriverConfig,
)
from evidpath.schema import AgentState, Observation, ScenarioConfig, ScenarioContext


def test_in_process_search_driver_calls_function() -> None:
    def search(request):
        assert request.query == "weather alerts"
        return SearchResponse(
            request_id=request.request_id,
            results=(
                SearchResult(
                    result_id="r1",
                    title="Weather Alerts",
                    snippet="Current warnings.",
                    url="https://example.com/weather",
                    result_type="news",
                    relevance_score=0.91,
                    rank=1,
                ),
            ),
        )

    _register_module("evidpath_test_search_function", {"search": search})
    driver = InProcessSearchDriver(
        InProcessSearchDriverConfig(import_path="evidpath_test_search_function:search")
    )

    ranked_list = driver.get_ranked_list(
        _dummy_state(),
        _dummy_observation(),
        _dummy_scenario(),
    )

    assert ranked_list.items[0].item_id == "r1"
    assert ranked_list.items[0].score == pytest.approx(0.91)
    assert driver.check_health() == {"status": "ok"}


def test_in_process_search_driver_calls_class_search_and_collects_metadata() -> None:
    class Backend:
        service_metadata = {"model_id": "search-v1"}

        def search(self, request):
            return SearchResponse(request_id=request.request_id, results=())

    _register_module("evidpath_test_search_class", {"Backend": Backend})
    driver = InProcessSearchDriver(
        InProcessSearchDriverConfig(
            import_path="evidpath_test_search_class:Backend",
            backend_name="local-search",
        )
    )

    metadata = driver.get_service_metadata()

    assert metadata["service_kind"] == "in_process"
    assert metadata["backend_name"] == "local-search"
    assert metadata["model_id"] == "search-v1"


def _register_module(name: str, attrs: dict[str, object]) -> None:
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


def _dummy_state() -> AgentState:
    return AgentState(
        agent_id="agent-1",
        archetype_label="archetype",
        step_index=0,
        click_threshold=0.5,
        preferred_genres=("news",),
        popularity_preference=0.5,
        novelty_preference=0.4,
        repetition_tolerance=0.6,
        sparse_history_confidence=0.5,
        abandonment_sensitivity=0.2,
        engagement_baseline=0.5,
        quality_sensitivity=0.6,
        repeat_exposure_penalty=0.1,
        novelty_fatigue=0.1,
        frustration_recovery=0.3,
        history_reliance=0.4,
        skip_tolerance=1,
        abandonment_threshold=0.85,
        patience_remaining=2,
        last_action="start",
        history_item_ids=(),
    )


def _dummy_observation() -> Observation:
    return Observation(
        session_id="session-1",
        step_index=0,
        max_steps=2,
        available_actions=("click", "skip"),
        scenario_context=ScenarioContext(
            scenario_name="search-scenario",
            history_depth=0,
            history_item_ids=(),
            description="",
            scenario_id="search-scenario",
            runtime_profile="",
            context_hint="weather alerts",
        ),
    )


def _dummy_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="search-scenario",
        max_steps=2,
        allowed_actions=("click", "skip"),
        history_depth=0,
        description="",
        scenario_id="search-scenario",
        test_goal="",
        runtime_profile="",
        context_hint="",
    )
