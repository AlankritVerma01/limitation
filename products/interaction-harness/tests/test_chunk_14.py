from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from interaction_harness.adapters.http import HttpRecommenderAdapter
from interaction_harness.audit import execute_recommender_audit, write_run_artifacts
from interaction_harness.domains.recommender.inputs import project_recommender_scenarios
from interaction_harness.domains.recommender.policy import (
    build_seeded_archetypes,
    initial_state_from_seed,
)
from interaction_harness.population_generation import (
    generate_population_pack,
    project_recommender_population,
)
from interaction_harness.scenario_generation import (
    build_scenario_pack,
    generate_scenario_pack,
)
from interaction_harness.scenarios.recommender import (
    resolve_built_in_recommender_scenarios,
)
from interaction_harness.schema import ScenarioContext
from interaction_harness.services.reference_artifacts import ensure_reference_artifacts
from interaction_harness.services.reference_recommender import (
    run_reference_recommender_service,
)


def test_built_in_recommender_scenarios_now_include_broader_session_families() -> None:
    scenarios = resolve_built_in_recommender_scenarios()

    assert {scenario.name for scenario in scenarios} == {
        "returning-user-home-feed",
        "sparse-history-home-feed",
        "taste-elicitation-home-feed",
        "re-engagement-home-feed",
    }


def test_generated_scenarios_can_project_into_broader_runtime_profiles() -> None:
    pack = generate_scenario_pack(
        "test onboarding and re-engagement quality for movie discovery",
        generator_mode="fixture",
        scenario_count=6,
    )

    projected = project_recommender_scenarios(pack)

    assert {
        scenario.runtime_profile for scenario in projected
    } >= {
        "taste-elicitation-home-feed",
        "re-engagement-home-feed",
    }


def test_generated_population_projection_preserves_behavior_metadata() -> None:
    pack = generate_population_pack(
        "test a recommender for risk-sensitive but curious viewers",
        generator_mode="fixture",
        population_size=6,
        candidate_count=12,
    )

    runtime_seeds = project_recommender_population(pack)

    assert len(pack.personas) == len(runtime_seeds)
    assert all(persona.behavior_goal for persona in pack.personas)
    assert all(runtime_seed.behavior_goal for runtime_seed in runtime_seeds)
    assert all(runtime_seed.diversity_tags for runtime_seed in runtime_seeds)


def test_scenario_and_persona_context_shape_initial_state_more_directly() -> None:
    base_seed = build_seeded_archetypes()[0]
    generated_like_seed = replace(
        base_seed,
        behavior_goal="Reward exploration without a weak first impression.",
        diversity_tags=("novelty-seeking", "first-impression-sensitive"),
    )

    plain_context = ScenarioContext(
        scenario_name="returning-user-home-feed",
        runtime_profile="returning-user-home-feed",
        history_depth=4,
        history_item_ids=("action-1", "comedy-1"),
        description="Plain context.",
        context_hint="steady returning session",
        risk_focus_tags=(),
    )
    shaped_context = ScenarioContext(
        scenario_name="taste-elicitation-home-feed",
        runtime_profile="taste-elicitation-home-feed",
        history_depth=0,
        history_item_ids=(),
        description="Taste elicitation context.",
        context_hint="novel fresh onboarding session where first impression matters",
        risk_focus_tags=("cold-start", "weak-first-impression", "novelty-mismatch"),
    )

    base_state = initial_state_from_seed(base_seed, plain_context)
    shaped_state = initial_state_from_seed(generated_like_seed, shaped_context)

    assert shaped_state.click_threshold != base_state.click_threshold
    assert shaped_state.confidence != base_state.confidence
    assert shaped_state.behavior_goal
    assert shaped_state.scenario_risk_focus_tags


def test_behavioral_signals_are_emitted_in_trace_scores_and_results(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    run_result = execute_recommender_audit(
        seed=11,
        output_dir=str(tmp_path / "audit"),
        scenario_names=("taste-elicitation-home-feed",),
        service_artifact_dir=str(artifact_dir),
    )
    write_run_artifacts(run_result)
    payload = json.loads(
        Path(run_result.run_config.rollout.output_dir, "results.json").read_text(
            encoding="utf-8"
        )
    )

    assert all(0.0 <= score.first_impression_score <= 1.0 for score in run_result.trace_scores)
    assert all(0.0 <= score.abandonment_pressure <= 1.0 for score in run_result.trace_scores)
    assert "mean_first_impression_score" in payload["summary"]
    assert "mean_abandonment_pressure" in payload["summary"]
    assert payload["summary"]["artifact_contract_version"] == "v1"


def test_generated_scenario_pack_changes_runtime_behavior_vs_builtin(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    builtin_result = execute_recommender_audit(
        seed=4,
        output_dir=str(tmp_path / "builtin"),
        scenario_names=("returning-user-home-feed",),
        service_artifact_dir=str(artifact_dir),
    )
    custom_pack = build_scenario_pack(
        [
            {
                "scenario_id": "generated-risky-returning",
                "name": "Generated risky returning session",
                "description": "Returning session with stronger trust and first-impression pressure.",
                "test_goal": "Verify context shaping changes runtime behavior.",
                "risk_focus_tags": ["weak-first-impression", "trust-drop", "staleness"],
                "max_steps": 5,
                "allowed_actions": ["click", "skip", "abandon"],
                "adapter_hints": {
                    "recommender": {
                        "runtime_profile": "returning-user-home-feed",
                        "history_depth": 4,
                        "context_hint": "fresh but trustworthy returning session where first impression matters",
                    }
                },
            }
        ],
        brief="generated returning context",
        generator_mode="fixture",
        generated_at_utc="2026-01-01T00:00:00+00:00",
        domain_label="recommender",
    )
    from interaction_harness.scenario_generation import write_scenario_pack

    pack_path = tmp_path / "scenario-pack.json"
    write_scenario_pack(custom_pack, pack_path)
    generated_result = execute_recommender_audit(
        seed=4,
        output_dir=str(tmp_path / "generated"),
        scenario_pack_path=str(pack_path),
        service_artifact_dir=str(artifact_dir),
    )

    builtin_mean = sum(score.first_impression_score for score in builtin_result.trace_scores) / len(
        builtin_result.trace_scores
    )
    generated_mean = sum(
        score.first_impression_score for score in generated_result.trace_scores
    ) / len(generated_result.trace_scores)

    assert builtin_mean != generated_mean


def test_external_url_metadata_is_clear_and_unreachable_targets_fail_cleanly(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    with run_reference_recommender_service(str(artifact_dir)) as (base_url, _metadata):
        run_result = execute_recommender_audit(
            seed=6,
            output_dir=str(tmp_path / "audit"),
            adapter_base_url=base_url,
        )

    assert run_result.metadata["target_endpoint_host"]
    assert run_result.metadata["service_metadata_status"] == "available"

    adapter = HttpRecommenderAdapter("http://127.0.0.1:1", timeout_seconds=0.1)
    state = run_result.traces[0].steps[0].agent_state_before
    observation = run_result.traces[0].steps[0].observation
    scenario_config = run_result.run_config.scenarios[0]
    with pytest.raises(RuntimeError) as exc_info:
        adapter.get_slate(state, observation, scenario_config)

    assert "unreachable" in str(exc_info.value).lower() or "failed during" in str(exc_info.value).lower()
