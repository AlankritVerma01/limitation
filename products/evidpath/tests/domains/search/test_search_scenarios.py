"""Tests for built-in search scenarios."""

from __future__ import annotations

import pytest
from evidpath.domains.search import (
    BUILT_IN_SEARCH_SCENARIO_NAMES,
    build_scenarios,
    resolve_built_in_search_scenarios,
)
from evidpath.schema import AgentSeed, RolloutConfig, RunConfig, ScoringConfig


def test_search_scenario_library_covers_expected_archetypes() -> None:
    assert BUILT_IN_SEARCH_SCENARIO_NAMES == (
        "navigational-query",
        "informational-long-tail-query",
        "time-sensitive-query",
        "ambiguous-query",
        "typo-query",
        "zero-result-query",
        "personalized-vs-anonymous-query",
    )


def test_search_scenario_initializes_query_context() -> None:
    config = resolve_built_in_search_scenarios(("time-sensitive-query",))[0]
    scenario = build_scenarios((config,))[0]

    observation = scenario.initialize(_agent_seed(), _run_config((config,)))

    assert observation.scenario_context.context_hint == "current weather alerts toronto"
    assert observation.scenario_context.runtime_profile == "time-sensitive"
    assert observation.available_actions == ("click", "skip", "abandon")


def test_unknown_search_scenario_names_raise_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown scenario names"):
        resolve_built_in_search_scenarios(("missing",))


def _agent_seed() -> AgentSeed:
    return AgentSeed(
        agent_id="agent-1",
        archetype_label="searcher",
        preferred_genres=("news", "article"),
        popularity_preference=0.5,
        novelty_preference=0.5,
        repetition_tolerance=0.5,
        sparse_history_confidence=0.5,
        abandonment_sensitivity=0.5,
        patience=1,
        engagement_baseline=0.5,
        quality_sensitivity=0.5,
        repeat_exposure_penalty=0.1,
        novelty_fatigue=0.1,
        frustration_recovery=0.2,
        history_reliance=0.5,
        skip_tolerance=1,
        abandonment_threshold=0.8,
    )


def _run_config(scenarios) -> RunConfig:
    return RunConfig(
        run_name="search-test",
        scenarios=tuple(scenarios),
        rollout=RolloutConfig(
            seed=0,
            output_dir="tmp",
            service_mode="reference",
            service_artifact_dir=None,
            adapter_base_url=None,
            service_timeout_seconds=2.0,
        ),
        scoring=ScoringConfig(),
        agent_seeds=(_agent_seed(),),
    )
